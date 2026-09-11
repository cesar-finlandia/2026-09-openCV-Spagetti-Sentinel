# Requirement IDs: MED-01, MED-02, MED-03, MED-04, MED-REU-01, MED-REU-02,
# MED-RES-01, MED-RES-02, RES-REU-02, GOV-RES-01, GOV-RES-04, XCUT-08
"""STT public entrypoint (Python) — DP-C §4.1.

Layout note: this entrypoint is the PACKAGE ``src/media/stt/`` rather than a
``stt.py`` module because the design-plan tree also places ``stt/providers/``
beside it and a same-named module+package cannot coexist in one directory.
``from src.media.stt import transcribe`` behaves exactly like the TS
``import { transcribe } from "src/media/stt"``.

transcribe(input, opts?) normalizes raw audio input, applies the §7.2 error
contract (bad-input codes RETURNED as UnifiedMediaMessage["error"]; provider
failures RAISED as MediaError so RES-01 can retry/fallback), resolves the
provider at call time via get_stt_provider(config.provider) (MED-03 env swap),
and bounds every path with timeout_ms (default 15000 — never silent hang).

Isolation (MED-REU-02 / §8.1): imports ONLY media-message types, media config,
its own stt.providers.* — never vision/pdf/tts.
"""

from __future__ import annotations

import asyncio
import base64 as _b64
from pathlib import Path
from typing import Any

from src.media.config import MediaError, load_media_config
from src.media.media_message import UnifiedMediaMessage

from .providers import deepgram as _deepgram
from .providers import openai_whisper as _openai_whisper
from .providers import synthetic_fixture as _synthetic_fixture
from .providers.types import (
    AudioInput,
    SttOptions,
    get_stt_provider,
    register_stt_provider,
)

__all__ = [
    "AudioInput",
    "SttOptions",
    "add_stt_provider",
    "transcribe",
    "transcribe_async",
    "transcribe_sync",
    "validate_audio_buffer",
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
    import datetime as _dt

    return UnifiedMediaMessage(
        type="stt",
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

# Built-in registration (DP-C §4.1 — synthetic-fixture ALWAYS available)
_synthetic_fixture.register()
_openai_whisper.register()
_deepgram.register()


def add_stt_provider(provider: Any) -> None:
    """Register an additional provider at runtime (Engine-supplied backends)."""
    register_stt_provider(provider)


# ---------------------------------------------------------------------------
# Input validation helpers (MED-RES-02 / DP-C §7.2)
# ---------------------------------------------------------------------------

_SUPPORTED_ENCODINGS = {"wav", "wave", "mp3", "webm", "ogg"}
_WAV_MIN_BYTES = 44  # RIFF(12) + fmt(24) + data header(8)


def _encoding_of(input: AudioInput) -> str | None:
    if isinstance(input, dict):
        enc = input.get("encoding")
        return str(enc).lower() if enc else None
    if isinstance(input, str):
        ext = input.rsplit(".", 1)[-1] if "." in input else ""
        return ext.lower() or None
    return None


def materialize_bytes(input: AudioInput) -> bytes:
    """Materialize path/buffer/base64 inputs to bytes (streams are collected
    by transcribe_async under its own bound; transcribe() rejects them)."""
    if isinstance(input, dict):
        if "path" in input:
            return Path(str(input["path"])).read_bytes()
        if "buffer" in input:
            return bytes(input["buffer"])
        if "base64" in input:
            return _b64.b64decode(input["base64"])
        raise MediaError("provider_error", "stream inputs require transcribe_async()")
    if isinstance(input, bytes):
        return input
    if isinstance(input, str):
        return Path(input).read_bytes()
    raise MediaError("provider_error", "unsupported AudioInput variant")


def validate_audio_buffer(encoding: str | None, data: bytes) -> str | None:
    """Classify one materialized buffer per the §4.1 failure table.

    Returns None when OK, otherwise the error code to place on the message:
    empty_input | corrupt_file | unsupported_format."""
    if len(data) == 0:
        return "empty_input"
    if encoding is not None and encoding not in _SUPPORTED_ENCODINGS:
        return "unsupported_format"
    starts_riff = len(data) >= 4 and data[0:4] == b"RIFF"
    complete_wav = starts_riff and len(data) >= _WAV_MIN_BYTES and data[8:12] == b"WAVE"
    claims_wav = encoding in ("wav", "wave") or starts_riff
    if claims_wav and not complete_wav:
        return "corrupt_file"
    return None


def _raw_ref_of(input: AudioInput) -> str:
    if isinstance(input, str):
        return input
    if isinstance(input, dict):
        if "path" in input:
            return str(input["path"])
        if "buffer" in input:
            return f"buffer:{len(input['buffer'])}b"
        if "base64" in input:
            return "base64:inline"
        return "stream:inline"
    if isinstance(input, bytes):
        return f"buffer:{len(input)}b"
    return "stream:inline"


def _error_message(raw_ref: str, provider: str, code: str) -> UnifiedMediaMessage:
    return _message(raw_ref=raw_ref, provider=provider, error=code)


def _finalize(raw_ref: str, provider_id: str, result: dict[str, Any]) -> UnifiedMediaMessage:
    structured = result.get("structured") or {}
    words = structured.get("words")
    confidence = float(result.get("confidence", 0.0))
    return _message(
        raw_ref=raw_ref,
        provider=provider_id,
        text=result.get("text", ""),
        structured_fields={
            "language": structured.get("language"),
            "duration_ms": structured.get("duration_ms"),
            "words": words if isinstance(words, list) else [],
        },
        confidence=min(1.0, max(0.0, confidence)),
        # MED-04/NONGOAL-06 provenance: true iff produced by the checked-in
        # synthetic fixture provider.
        synthetic=(provider_id == "synthetic-fixture"),
    )


# ---------------------------------------------------------------------------
# transcribe / transcribe_sync / transcribe_async (DP-C §4.1/§7.1/§7.2)
# ---------------------------------------------------------------------------


def _run_provider(provider_id: str, input: AudioInput, opts: SttOptions) -> dict[str, Any]:
    """Resolve + invoke a provider; normalize foreign exceptions to MediaError
    (provider_error) so RES-01 sees typed failures (never swallowed)."""
    provider = get_stt_provider(provider_id)
    if provider is None:
        raise MediaError("unknown_provider", f'no STT provider registered under id "{provider_id}"')
    try:
        return dict(provider.transcribe(input, opts))
    except MediaError:
        raise
    except Exception as err:
        raise MediaError("provider_error", f'stt provider "{provider_id}" failed: {err}') from err


def _validate_or_none(input: AudioInput) -> tuple[str | None, bytes | None]:
    """(error_code_or_None, materialized_bytes_or_None_for_streams)."""
    if isinstance(input, dict) and "stream" in input:
        return None, None  # streams are collected under the async bound only
    data = materialize_bytes(input)
    return validate_audio_buffer(_encoding_of(input), data), data


def transcribe_sync(input: AudioInput, opts: SttOptions | None = None) -> UnifiedMediaMessage:
    """Synchronous transcribe (DP-C §4.1). Bad input → message with typed
    `error` code and NO provider call; provider failure → raised MediaError."""
    if isinstance(input, dict) and "stream" in input:
        raise MediaError("provider_error", "stream inputs require transcribe_async()")
    config = load_media_config("stt", opts or None)
    raw_ref = _raw_ref_of(input)
    bad_code, _data = _validate_or_none(input)
    if bad_code is not None:
        return _error_message(raw_ref, config["provider"], bad_code)
    result = _run_provider(config["provider"], input, opts or {})
    return _finalize(raw_ref, config["provider"], result)


def transcribe(input: AudioInput, opts: SttOptions | None = None) -> UnifiedMediaMessage:
    """Blocking convenience alias of transcribe_sync — mirrors the DP-C §9.1
    Python usage ``msg = transcribe({"path": ...}, {"provider": ...})``.
    The offline fixture path returns immediately; use transcribe_async for
    timeout-bounded network providers."""
    return transcribe_sync(input, opts)


async def transcribe_async(input: AudioInput, opts: SttOptions | None = None) -> UnifiedMediaMessage:
    """Async transcribe with a hard timeout bound on every path (§7.2 — never
    silent hang). Streams are collected under the bound; provider calls run in
    a worker thread so a stuck SDK cannot block the loop past timeout_ms."""
    config = load_media_config("stt", opts or None)
    timeout_s = float(config.get("timeout_ms") or 15000) / 1000.0
    loop = asyncio.get_running_loop()

    def _prologue() -> tuple[str, str | None]:
        raw_ref = _raw_ref_of(input)
        if isinstance(input, dict) and "stream" in input:
            data = input["stream"].read()
            return raw_ref, validate_audio_buffer(_encoding_of(input), data)
        bad_code, _data = _validate_or_none(input)
        return raw_ref, bad_code

    raw_ref, bad_code = await asyncio.wait_for(
        loop.run_in_executor(None, _prologue), timeout=timeout_s
    )
    if bad_code is not None:
        return _error_message(raw_ref, config["provider"], bad_code)
    result = await asyncio.wait_for(
        loop.run_in_executor(None, _run_provider, config["provider"], input, opts or {}),
        timeout=timeout_s,
    )
    return _finalize(raw_ref, config["provider"], result)
