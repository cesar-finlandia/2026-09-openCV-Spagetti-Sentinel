# Requirement IDs: MED-03, MED-TTS-01, MED-RES-01, GOV-MIN-04, GOV-RES-02,
# XCUT-08
"""openai-tts provider — Python mirror of openai-tts.ts (audio/speech API).

Request/RESPONSE only today: no native synthesize_stream is exposed, so the
wrapper polyfills streaming by slicing the synthesized bytes (DP-C §5.1) and
the MED-TTS-01 incremental contract holds without caller changes.

Stdlib-only HTTP (GOV-MIN-04): uses urllib.request; an absent credential
surfaces as a RAISED MediaError at call time so RES-01 can retry/fallback.
The credential VALUE is read via resolve_credential() using only the env var
NAME held in credentials_env (GOV-RES-02 indirection). Model default tts-1.
NONGOAL-04: `voice` is a plain provider voice-id passthrough ("alloy"...).
"""

from __future__ import annotations

import json
import urllib.request

from src.media.config import MediaError, resolve_credential

from .types import TtsInput, TtsOptions, TtsProvider, TtsResult, register_tts_provider

_URL = "https://api.openai.com/v1/audio/speech"
_DEFAULT_SAMPLE_RATES = {"mp3": 44100, "wav": 44100, "pcm": 24000}


def _text_of(input: TtsInput) -> str:
    return input if isinstance(input, str) else str(input.get("text", ""))


class OpenaiTtsProvider:
    id = "openai-tts"

    def synthesize(self, input: TtsInput, opts: TtsOptions | None = None) -> TtsResult:
        opts = opts or {}
        # Credential first — call-time check (GOV-RES-02); raises
        # MediaError("missing_credentials") when the named env var is unset.
        api_key = resolve_credential(
            {"provider": self.id, "credentials_env": opts.get("credentials_env") or "OPENAI_API_KEY"}
        )
        fmt = str(opts.get("format") or "mp3")
        model = opts.get("model") or "tts-1"
        payload = {
            "model": model,
            "input": _text_of(input),
            "voice": opts.get("voice") or "alloy",
            "response_format": fmt,
        }
        req = urllib.request.Request(
            _URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=float(opts.get("timeout_ms") or 15000) / 1000.0) as res:
                audio = res.read()
        except Exception as err:
            raise MediaError("provider_error", f"openai-tts synthesis failed: {err}") from err
        return TtsResult(
            audio=audio,
            format=fmt,
            sample_rate=int(opts.get("sampleRate") or opts.get("sample_rate") or _DEFAULT_SAMPLE_RATES.get(fmt, 24000)),
            duration_ms=None,
            audio_ref=None,  # inline base64 in structured_fields (§4.4 output note)
        )


_INSTANCE = OpenaiTtsProvider()


def register() -> None:
    from .types import register_tts_provider as _reg

    _reg(_INSTANCE)
