# Requirement IDs: MED-03, MED-TTS-01, MED-RES-01, GOV-MIN-04, GOV-RES-02,
# XCUT-08
"""elevenlabs TTS provider — Python mirror of elevenlabs.ts (RES-03 secondary).

Stdlib-only HTTP (GOV-MIN-04) against the stream-text-to-speech endpoint; an
absent credential surfaces as a RAISED MediaError at call time so RES-01 can
retry/fallback. The credential VALUE is read via resolve_credential() using
only the env var NAME held in credentials_env (GOV-RES-02 indirection).
Model default: eleven_multilingual_v2.

NATIVE STREAMING (DP-C §5.1): implements synthesize_stream by reading the
endpoint's chunked MP3 body incrementally, so first audio can play before
synthesis completes (MED-TTS-01) — no wrapper polyfill, no caller change.
NONGOAL-04: `voice` is a plain provider voice-id passthrough.
"""

from __future__ import annotations

import base64
import json
import time
import urllib.request
from typing import AsyncIterator

from src.media.config import MediaError, resolve_credential

from .types import TtsChunk, TtsInput, TtsOptions, TtsProvider, register_tts_provider

_API = "https://api.elevenlabs.io/v1/text-to-speech"
_DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # neutral "Rachel" voice id
_DEFAULT_MODEL = "eleven_multilingual_v2"


def _parts_of(input: TtsInput) -> tuple[str, str | None]:
    if isinstance(input, str):
        return input, None
    return str(input.get("text", "")), (input.get("voice") or None)


class ElevenLabsTtsProvider:
    id = "elevenlabs"

    def synthesize(self, input: TtsInput, opts: TtsOptions | None = None) -> dict:
        with self._open(input, opts) as res:
            audio = res.read()
        return {
            "audio": audio,
            "format": (opts or {}).get("format") or "mp3",
            "sample_rate": int((opts or {}).get("sampleRate") or (opts or {}).get("sample_rate") or 44100),
            "duration_ms": None,
            "audio_ref": None,
        }

    async def synthesize_stream(self, input: TtsInput, opts: TtsOptions | None = None) -> AsyncIterator[TtsChunk]:
        """Native incremental delivery (§5.1). The blocking HTTP read runs on a
        worker thread so the event loop stays responsive; the barge-in event is
        honoured between chunks and raises asyncio.CancelledError when set."""
        import asyncio

        opts = opts or {}
        signal = opts.get("signal")
        t0 = time.monotonic()

        loop = asyncio.get_running_loop()
        res = await loop.run_in_executor(None, self._open, input, opts)
        index = 0
        try:
            while True:
                if signal is not None and signal.is_set():
                    raise asyncio.CancelledError()
                chunk = await loop.run_in_executor(None, res.read1, 8192)
                if not chunk:
                    break
                yield TtsChunk(
                    audio_chunk=base64.b64encode(chunk).decode("ascii"),
                    delta_text="",  # byte-level stream; text alignment not provided
                    index=index,
                    is_final=False,
                    latency_ms=None,
                )
                index += 1
        finally:
            res.close()
        yield TtsChunk(
            audio_chunk="",
            delta_text="",
            index=index,
            is_final=True,
            latency_ms=int((time.monotonic() - t0) * 1000),
        )

    def _open(self, input: TtsInput, opts: TtsOptions | None):
        opts = opts or {}
        api_key = resolve_credential(
            {"provider": self.id, "credentials_env": opts.get("credentials_env") or "ELEVENLABS_API_KEY"}
        )
        text, voice = _parts_of(input)
        voice_id = voice or _DEFAULT_VOICE_ID
        req = urllib.request.Request(
            f"{_API}/{voice_id}?output_format=mp3_44100_128",
            data=json.dumps({"text": text, "model_id": opts.get("model") or _DEFAULT_MODEL}).encode("utf-8"),
            headers={"xi-api-key": api_key, "Content-Type": "application/json"},
            method="POST",
        )
        try:
            return urllib.request.urlopen(req, timeout=float(opts.get("timeout_ms") or 15000) / 1000.0)
        except Exception as err:
            raise MediaError("provider_error", f"elevenlabs synthesis failed: {err}") from err


_INSTANCE = ElevenLabsTtsProvider()


def register() -> None:
    from .types import register_tts_provider as _reg

    _reg(_INSTANCE)
