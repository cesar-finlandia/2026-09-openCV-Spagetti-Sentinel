# Requirement IDs: MED-01, MED-02, MED-TTS-01, MED-TTS-02, MED-TTS-03,
# MED-REU-01, MED-REU-02, MED-RES-01, MED-RES-02, RES-REU-02, GOV-RES-01,
# GOV-RES-04, XCUT-08
"""TTS public entrypoint (Python) — DP-C §4.4 (synthesize) + §5.1 (stream).

Layout note: this entrypoint is the PACKAGE ``src/media/tts/`` rather than a
``tts.py`` module because the design-plan tree also places ``tts/providers/``
beside it and a same-named module+package cannot coexist in one directory.
``from src.media.tts import synthesize`` behaves exactly like the TS
``import { synthesize } from "src/media/tts"``.

synthesize(input, opts?) applies the §7.2/§4.4 error contract: bad inputs
(empty, >5000 chars, unsupported format) are RETURNED as UnifiedMediaMessage
with a typed error BEFORE any provider call; provider failures are RAISED as
MediaError so RES-01 can retry/fallback. The provider resolves at call time via
get_tts_provider(config.provider) (MED_TTS_PROVIDER env swap, zero code change).

synthesize_stream(input, opts?) yields incremental TtsChunks (MED-TTS-01):
native provider streaming delegates verbatim; request/response providers are
polyfilled by slicing the synthesized bytes into 4KB base64 chunks. The barge-in
event opts["signal"] is honoured BEFORE every yield (and before the provider
fetch); abort raises asyncio.CancelledError which callers map to a final
error:"tts_interrupted" envelope (§5.2 — see README.md in this package).

Isolation (MED-REU-02 / DP-C §8.1): imports ONLY media-message types, media
config, its own tts.providers.* + barge_in — NEVER stt/vision/pdf.

NONGOAL-04: voice is a provider voice-id passthrough; no dialogue policy,
persona, or tone logic exists anywhere in this module.
"""

from __future__ import annotations

import asyncio
import base64 as _b64
import datetime as _dt
import hashlib as _hashlib
from typing import Any, AsyncIterator

from src.media.config import MediaError, load_media_config
from src.media.media_message import UnifiedMediaMessage

from .barge_in import BargeInController
from .providers import elevenlabs as _elevenlabs
from .providers import openai_tts as _openai_tts
from .providers import synthetic_fixture as _synthetic_fixture
from .providers.types import (
    TtsChunk,
    TtsInput,
    TtsOptions,
    get_tts_provider,
    has_native_stream,
    register_tts_provider,
)

__all__ = [
    "BargeInController",
    "TtsChunk",
    "TtsInput",
    "TtsInputError",
    "TtsOptions",
    "add_tts_provider",
    "synthesize",
    "synthesize_stream",
    "validate_tts_input",
]

# ---------------------------------------------------------------------------
# Built-in registration (DP-C §4.4 — synthetic-fixture ALWAYS available)
# ---------------------------------------------------------------------------

_synthetic_fixture.register()
_openai_tts.register()
_elevenlabs.register()


def add_tts_provider(provider: Any) -> None:
    """Register an additional provider at runtime (Engine-supplied backends)."""
    register_tts_provider(provider)


# ---------------------------------------------------------------------------
# Input validation (§4.4 failure table / MED-RES-02)
# ---------------------------------------------------------------------------

_MAX_TEXT_CHARS = 5000
_SUPPORTED_FORMATS = {"mp3", "wav", "pcm"}


class TtsInputError(Exception):
    """Typed error raised by synthesize_stream for bad input — a stream has no
    envelope channel mid-flight, so §4.4 bad-input codes surface here as
    exceptions; callers wanting UnifiedMediaMessage envelopes use synthesize()."""

    def __init__(self, code: str, message: str | None = None) -> None:
        super().__init__(message or code)
        self.code = code


def _text_of(input: TtsInput | None) -> str | None:
    if isinstance(input, str):
        return input
    if isinstance(input, dict):
        t = input.get("text")
        return t if isinstance(t, str) else None
    return None


def validate_tts_input(input: TtsInput | None, opts: TtsOptions | None = None) -> str | None:
    """Validate one TtsInput per the §4.4 failure table. Returns None when OK,
    otherwise the UnifiedMediaMessage error code to report:
    ""/None text → empty_input; >5000 chars → unsupported_format (no silent
    truncation); format outside mp3|wav|pcm → unsupported_format."""
    text = _text_of(input)
    if text is None or len(text) == 0:
        return "empty_input"
    if len(text) > _MAX_TEXT_CHARS:
        return "unsupported_format"  # caller may split
    fmt = (opts or {}).get("format")
    if fmt is not None and fmt not in _SUPPORTED_FORMATS:
        return "unsupported_format"
    return None


def _raw_ref_of(text: str) -> str:
    digest = _hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]
    return f"hash:{digest}:text:{text[:64]}"


# ---------------------------------------------------------------------------
# Message construction (UnifiedMediaMessage literal — schema §3.1/§3.3)
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
        type="tts",
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


def _finalize(provider_id: str, result: dict[str, Any], latency_ms: int) -> UnifiedMediaMessage:
    audio: bytes = result["audio"]
    structured: dict[str, Any] = {
        "audio_format": result.get("format") or "mp3",
        "sample_rate": result.get("sample_rate"),
        "duration_ms": result.get("duration_ms"),
        "chunk_index": 0,
        "is_final": True,
        **(
            {"audio_ref": result["audio_ref"]}
            if result.get("audio_ref")
            else {"audio_base64": _b64.b64encode(audio).decode("ascii")}
        ),
        "latency_ms": latency_ms,
        "barge_in_supported": True,
    }
    return _message(
        raw_ref=result["raw_ref"],
        provider=provider_id,
        text=result["text"],
        structured_fields=structured,
        confidence=1.0,
        synthetic=(provider_id == "synthetic-fixture"),
    )


# ---------------------------------------------------------------------------
# synthesize (main path — DP-C §4.4)
# ---------------------------------------------------------------------------


def _run_provider(provider_id: str, input: TtsInput, opts: TtsOptions) -> tuple[Any, Any]:
    """Resolve + invoke a provider; normalize foreign exceptions to MediaError
    (provider_error) so RES-01 sees typed failures (never swallowed).
    Returns (provider, result_dict)."""
    provider = get_tts_provider(provider_id)
    if provider is None:
        raise MediaError("unknown_provider", f'no TTS provider registered under id "{provider_id}"')
    try:
        return provider, dict(provider.synthesize(input, opts))
    except MediaError:
        raise
    except Exception as err:
        raise MediaError("provider_error", f'tts provider "{provider_id}" failed: {err}') from err


def synthesize(input: TtsInput, opts: TtsOptions | None = None) -> UnifiedMediaMessage:
    """Synthesize text to one UnifiedMediaMessage (type:"tts", text echoes
    input).

    - Bad input → message with error empty_input|unsupported_format,
      confidence 0, NO provider call (§4.4 failure table, MED-RES-02).
    - Unknown provider id → RAISES MediaError("unknown_provider") (§7.2).
    - Provider/network failure → RAISES normalized MediaError("provider_error")
      so RES-01 can retry/fallback (MED-RES-01); never swallowed into .error.
    """
    config = load_media_config("tts", opts or None)
    text = _text_of(input) or ""
    raw_ref = _raw_ref_of(text)

    # 1. Validate BEFORE any provider work (no provider call on bad input).
    bad_code = validate_tts_input(input, opts)
    if bad_code == "empty_input":
        return _message(raw_ref=raw_ref, provider=config["provider"], error="empty_input")
    if bad_code is not None:
        # >5000 chars keeps a marker instead of echoing megabytes (§4.4 table
        # row: unsupported_format with text "input_exceeds_limit").
        return _message(raw_ref=raw_ref, provider=config["provider"], text="input_exceeds_limit", error=bad_code)

    # 2+3. Resolve provider at CALL time and invoke; failures raise normalized.
    t0 = _dt.datetime.now()
    _provider, result = _run_provider(config["provider"], input, opts or {})
    latency_ms = int((_dt.datetime.now() - t0).total_seconds() * 1000)
    return _finalize(config["provider"], {**result, "raw_ref": raw_ref, "text": text}, latency_ms)


# ---------------------------------------------------------------------------
# synthesize_stream (MED-TTS-01 incremental delivery — DP-C §5.1)
# ---------------------------------------------------------------------------

_POLYFILL_SLICE_BYTES = 4096


async def synthesize_stream(
    input: TtsInput, opts: TtsOptions | None = None
) -> AsyncIterator[TtsChunk]:  # noqa: ANN201 — async generator
    """Stream synthesis incrementally as TtsChunks (MED-TTS-01). Native-
    streaming providers delegate verbatim; others are polyfilled by
    synthesizing whole and yielding 4KB base64 slices.

    - Bad input → RAISES TtsInputError (empty_input|unsupported_format) before
      the first yield (streams have no envelope channel; use synthesize()).
    - opts["signal"] (asyncio.Event) honoured before every yield AND before the
      provider fetch; abort raises asyncio.CancelledError. Callers map it to a
      final error:"tts_interrupted" envelope (§5.2 — see this package's README).
    """
    config = load_media_config("tts", opts or None)
    opts = opts or {}
    signal = opts.get("signal")

    # Validation before the first yield (§4.4 table — same codes as synthesize).
    bad_code = validate_tts_input(input, opts)
    if bad_code == "empty_input":
        raise TtsInputError("empty_input")
    if bad_code is not None:
        raise TtsInputError(bad_code, "input_exceeds_limit")

    # Cancellation check before the provider byte fetch (§5.2 semantics).
    if signal is not None and signal.is_set():
        raise asyncio.CancelledError()

    provider_id = config["provider"]
    provider = get_tts_provider(provider_id)
    if provider is None:
        raise MediaError("unknown_provider", f'no TTS provider registered under id "{provider_id}"')

    loop = asyncio.get_running_loop()

    if has_native_stream(provider):
        # Native path: delegate; honour abort before EVERY yield (§5.2).
        async for chunk in provider.synthesize_stream(input, opts):
            if signal is not None and signal.is_set():
                raise asyncio.CancelledError()
            yield chunk
        return

    # Polyfill (request/response providers): synthesize whole, slice to 4KB.
    def _synth() -> bytes:
        _, res = _run_provider(provider_id, input, opts)
        return bytes(res["audio"])

    audio = await loop.run_in_executor(None, _synth)
    index = 0
    start = 0
    while start < len(audio):
        if signal is not None and signal.is_set():
            raise asyncio.CancelledError()
        yield TtsChunk(
            audio_chunk=_b64.b64encode(audio[start : start + _POLYFILL_SLICE_BYTES]).decode("ascii"),
            delta_text="",  # not available in polyfill; native providers fill this
            index=index,
            is_final=start + _POLYFILL_SLICE_BYTES >= len(audio),
            latency_ms=None,
        )
        start += _POLYFILL_SLICE_BYTES
        index += 1
