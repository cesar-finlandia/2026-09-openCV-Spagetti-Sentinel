# Requirement IDs: MED-01, MED-02, MED-03, MED-04, MED-REU-01, MED-REU-02,
# MED-RES-01, MED-RES-02, RES-REU-02, GOV-RES-01, GOV-RES-04, XCUT-08
"""Vision public entrypoint (Python) — DP-C §4.2.

Layout note: this entrypoint is the PACKAGE ``src/media/vision/`` rather than a
``vision.py`` module because the design-plan tree also places
``vision/providers/`` beside it and a same-named module+package cannot coexist
in one directory. ``from src.media.vision import caption`` behaves exactly like
the TS ``import { caption } from "src/media/vision"``.

caption(input, opts?) normalizes raw image input, applies the §7.2 error
contract (bad-input codes RETURNED as UnifiedMediaMessage["error"]; provider
failures RAISED as MediaError so RES-01 can retry/fallback), resolves the
provider at call time via get_vision_provider(config.provider) (MED-03 env
swap), resolves the GENERIC prompt (default-prompt.txt ← config slice ←
opts.prompt — MED-REU-01), and bounds every path with timeout_ms via
caption_async (default 15000 — never silent hang).

Isolation (MED-REU-02 / §8.1): imports ONLY media-message types, media config,
its own vision.providers.* — never stt/pdf/tts.
"""

from __future__ import annotations

import base64 as _b64
import datetime as _dt
import os
import struct
from pathlib import Path
from typing import Any

from src.media.config import MediaError, load_media_config
from src.media.media_message import UnifiedMediaMessage

from .providers import anthropic_claude_vision as _anthropic_claude_vision
from .providers import openai_gpt4o_vision as _openai_gpt4o_vision
from .providers import synthetic_fixture as _synthetic_fixture
from .providers.types import (
    ImageInput,
    VisionOptions,
    default_prompt,
    get_vision_provider,
    register_vision_provider,
)

__all__ = [
    "ImageInput",
    "VisionOptions",
    "add_vision_provider",
    "caption",
    "caption_async",
    "caption_sync",
    "resolve_prompt",
    "validate_image_buffer",
]

# ---------------------------------------------------------------------------
# Message construction (UnifiedMediaMessage literal — schema §3.1)
# ---------------------------------------------------------------------------


def _message(
    *,
    raw_ref: str,
    provider: str,
    text: str = "",
    structured_fields: dict[str, Any] | None = None,
    confidence: float = 0.0,
    synthetic: bool = False,
    error: str | None = None,
) -> UnifiedMediaMessage:
    return UnifiedMediaMessage(
        type="vision",
        raw_ref=raw_ref,
        text=text,
        structured_fields=structured_fields,
        confidence=confidence,
        synthetic=synthetic,
        timestamp=_dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        provider=provider,
        error=error,
        version="1.0.0",
    )


# Built-in registration (DP-C §4.2 — synthetic-fixture ALWAYS available)
_synthetic_fixture.register()
_openai_gpt4o_vision.register()
_anthropic_claude_vision.register()


def add_vision_provider(provider: Any) -> None:
    """Register an additional provider at runtime (Engine-supplied backends)."""
    register_vision_provider(provider)


# ---------------------------------------------------------------------------
# Input validation helpers (MED-RES-02 / DP-C §7.2 failure table)
# ---------------------------------------------------------------------------

_SUPPORTED_FORMATS = {"png", "jpeg", "jpg", "webp"}
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_JPEG_MAGIC = b"\xff\xd8\xff"


def _ext_format(path: str) -> str:
    return path.rsplit(".", 1)[-1].lower() if "." in path else ""


def _mime_format(mime: str) -> str:
    return mime.rsplit("/", 1)[-1].lower() if "/" in mime else ""


def _declared_format(input: ImageInput) -> str | None:
    """Format DECLARED by the input: explicit mime wins, else path extension."""
    if isinstance(input, dict):
        if input.get("mime"):
            return _mime_format(str(input["mime"]))
        if isinstance(input.get("path"), str):
            return _ext_format(str(input["path"]))
    if isinstance(input, str):
        return _ext_format(input)
    return None


def _sniff_format(data: bytes) -> str | None:
    """Format SNIFFED from magic bytes: png | jpeg | webp | None (unknown)."""
    if data[:8] == _PNG_MAGIC:
        return "png"
    if data[:3] == _JPEG_MAGIC:
        return "jpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def validate_image_buffer(input: ImageInput, data: bytes) -> str | None:
    """Classify one materialized image buffer per the §4.2 failure table.

    Returns None when OK, otherwise the error code for the message:
    empty_input | unsupported_format (e.g. image/tiff) | corrupt_file
    (unknown magic / declared-vs-sniffed mismatch / truncated PNG-JPEG)."""
    if len(data) == 0:
        return "empty_input"
    declared = _declared_format(input)
    if declared and declared not in _SUPPORTED_FORMATS:
        return "unsupported_format"
    sniffed = _sniff_format(data)
    if sniffed is None:
        return "corrupt_file"
    if declared and declared != sniffed and not (declared == "jpg" and sniffed == "jpeg"):
        return "corrupt_file"  # declared type contradicts actual bytes
    complete = True
    if sniffed == "png":
        # Final chunk is always the 12-byte IEND chunk: len=0 + "IEND" + CRC.
        complete = len(data) >= 33 and data[-12:-8] == b"\x00\x00\x00\x00" and data[-8:-4] == b"IEND"
    elif sniffed == "jpeg":
        complete = len(data) >= 4 and data[-2:] == b"\xff\xd9"  # EOI marker
    return None if complete else "corrupt_file"


def image_dimensions(data: bytes) -> dict[str, int] | None:
    """Pixel dimensions when cheaply parseable: PNG IHDR / JPEG SOF markers;
    None otherwise (providers may still report their own dimensions)."""
    fmt = _sniff_format(data)
    if fmt == "png" and len(data) >= 24:
        width, height = struct.unpack(">II", data[16:24])
        return {"width": width, "height": height}
    if fmt != "jpeg":
        return None
    off = 2
    while off + 9 < len(data):
        if data[off] != 0xFF:
            break
        marker = data[off + 1]
        seg_len = struct.unpack(">H", data[off + 2 : off + 4])[0]
        if 0xC0 <= marker <= 0xC3:
            height, width = struct.unpack(">HH", data[off + 5 : off + 9])
            return {"width": width, "height": height}
        off += 2 + seg_len
    return None


def materialize_bytes(input: ImageInput) -> bytes:
    """Materialize path/buffer/base64 inputs to bytes (urls are fetched only by
    caption_async under its bound; caption_sync reports them as
    unsupported_format when offline)."""
    if isinstance(input, dict):
        if "path" in input:
            return Path(str(input["path"])).read_bytes()
        if "buffer" in input:
            return bytes(input["buffer"])
        if "base64" in input:
            return _b64.b64decode(input["base64"])
        raise MediaError("provider_error", "url inputs require caption_async()")
    if isinstance(input, bytes):
        return input
    if isinstance(input, str):
        return Path(input).read_bytes()
    raise MediaError("provider_error", "unsupported ImageInput variant")


def _raw_ref_of(input: ImageInput) -> str:
    if isinstance(input, str):
        return input
    if isinstance(input, dict):
        if "path" in input:
            return str(input["path"])
        if "buffer" in input:
            return f"buffer:{len(input['buffer'])}b"
        if "base64" in input:
            return "base64:inline"
        return f"url:{input.get('url', '')}"
    if isinstance(input, bytes):
        return f"buffer:{len(input)}b"
    return "stream:inline"


def _error_message(raw_ref: str, provider: str, code: str) -> UnifiedMediaMessage:
    return _message(raw_ref=raw_ref, provider=provider, error=code)


def _finalize(
    raw_ref: str,
    provider_id: str,
    result: dict[str, Any],
    dimensions: dict[str, int] | None,
    prompt_used: str,
) -> UnifiedMediaMessage:
    structured = result.get("structured") or {}
    objects = structured.get("objects")
    dims = structured.get("dimensions")
    used = structured.get("prompt_used")
    confidence = float(result.get("confidence", 0.0))
    return _message(
        raw_ref=raw_ref,
        provider=provider_id,
        text=result.get("text", ""),
        structured_fields={
            "objects": objects if isinstance(objects, list) else [],
            "dimensions": dims if isinstance(dims, dict) else dimensions,
            "prompt_used": used if isinstance(used, str) else prompt_used,
        },
        confidence=min(1.0, max(0.0, confidence)),
        # MED-04/NONGOAL-06 provenance: true iff produced by the checked-in
        # synthetic fixture provider.
        synthetic=(provider_id == "synthetic-fixture"),
    )


class _OfflineUrlError(Exception):
    """Sentinel for url inputs rejected offline (§4.2) — mapped to the typed
    unsupported_format message by the caption paths."""


def _fetch_url_image(url: str) -> bytes:
    import urllib.request

    if os.environ.get("NETWORK") == "disabled":
        raise _OfflineUrlError(f"offline mode: url inputs are disabled ({url})")
    with urllib.request.urlopen(url, timeout=15) as resp:  # noqa: S310 - caller-provided url
        return resp.read()


def resolve_prompt(opts: VisionOptions | None = None, config_prompt: str | None = None) -> str:
    """Generic-prompt resolution (MED-REU-01 / DP-C §6.2): per-call opts.prompt
    overrides config.prompt (which carries MED_VISION_PROMPT); null → checked-
    in default-prompt.txt. Persona prompts are forbidden by CI grep guard."""
    from_call = str(opts.get("prompt") or "").strip() if isinstance(opts, dict) else ""
    if from_call:
        return from_call
    from_config = str(config_prompt or "").strip()
    if from_config:
        return from_config
    return default_prompt()


def _run_provider(provider_id: str, input: ImageInput, opts: VisionOptions) -> dict[str, Any]:
    """Resolve + invoke a provider; normalize foreign exceptions to MediaError
    (provider_error) so RES-01 sees typed failures (never swallowed)."""
    provider = get_vision_provider(provider_id)
    if provider is None:
        raise MediaError("unknown_provider", f'no vision provider registered under id "{provider_id}"')
    try:
        return dict(provider.caption(input, opts))
    except MediaError:
        raise
    except Exception as err:
        raise MediaError("provider_error", f'vision provider "{provider_id}" failed: {err}') from err


def caption_sync(input: ImageInput, opts: VisionOptions | None = None) -> UnifiedMediaMessage:
    """Synchronous caption (DP-C §4.2). Bad input → message with typed `error`
    code and NO provider call; provider failure → raised MediaError."""
    if isinstance(input, dict) and "url" in input and os.environ.get("NETWORK") == "disabled":
        config = load_media_config("vision", opts or None)
        return _error_message(_raw_ref_of(input), config["provider"], "unsupported_format")
    config = load_media_config("vision", opts or None)
    raw_ref = _raw_ref_of(input)
    try:
        data = materialize_bytes(input)
    except _OfflineUrlError:
        return _error_message(raw_ref, config["provider"], "unsupported_format")
    bad_code = validate_image_buffer(input, data)
    if bad_code is not None:
        return _error_message(raw_ref, config["provider"], bad_code)
    dims = image_dimensions(data)
    effective = dict(opts or {})
    effective.setdefault("prompt", resolve_prompt(opts, config.get("prompt")))
    result = _run_provider(config["provider"], input, effective)
    return _finalize(raw_ref, config["provider"], result, dims, str(effective.get("prompt", "")))


def caption(input: ImageInput, opts: VisionOptions | None = None) -> UnifiedMediaMessage:
    """Blocking convenience alias of caption_sync — mirrors the DP-C §9.1
    Python usage ``msg = caption({"path": ...}, {"provider": ...})``.
    The offline fixture path returns immediately; use caption_async for
    timeout-bounded network providers."""
    return caption_sync(input, opts)


async def caption_async(input: ImageInput, opts: VisionOptions | None = None) -> UnifiedMediaMessage:
    """Async caption with a hard timeout bound on every path (§7.2 — never
    silent hang). Urls are fetched under the bound; provider calls run in a
    worker thread so a stuck SDK cannot block the loop past timeout_ms."""
    import asyncio

    config = load_media_config("vision", opts or None)
    timeout_s = float(config.get("timeout_ms") or 15000) / 1000.0
    loop = asyncio.get_running_loop()

    def _prologue() -> tuple[str, str | None, bytes | None]:
        raw_ref = _raw_ref_of(input)
        if isinstance(input, dict) and "url" in input:
            try:
                data = _fetch_url_image(str(input["url"]))
            except _OfflineUrlError:
                return raw_ref, "unsupported_format", None
            return raw_ref, validate_image_buffer(input, data), data
        data = materialize_bytes(input)
        return raw_ref, validate_image_buffer(input, data), data

    raw_ref, bad_code, _data = await asyncio.wait_for(
        loop.run_in_executor(None, _prologue), timeout=timeout_s
    )
    if bad_code is not None:
        return _error_message(raw_ref, config["provider"], bad_code)
    dims = image_dimensions(_data) if _data else None
    effective = dict(opts or {})
    effective.setdefault("prompt", resolve_prompt(opts, config.get("prompt")))
    result = await asyncio.wait_for(
        loop.run_in_executor(None, _run_provider, config["provider"], input, effective),
        timeout=timeout_s,
    )
    return _finalize(raw_ref, config["provider"], result, dims, str(effective.get("prompt", "")))
