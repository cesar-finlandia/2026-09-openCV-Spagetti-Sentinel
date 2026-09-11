# Requirement IDs: MED-03, MED-RES-01, GOV-MIN-04, GOV-RES-02, XCUT-08
"""deepgram STT provider — Python mirror of deepgram.ts (optional, RES-03
secondary).

Optional-dep style (GOV-MIN-04): no SDK import; transcription uses urllib over
HTTPS when selected. A missing DEEPGRAM_API_KEY (via credentials_env NAME
indirection) raises MediaError("missing_credentials") at CALL time — never at
startup — so RES-01 can fall back. Provider/network failures raise
MediaError("provider_error"); never swallowed into UnifiedMediaMessage.error.
"""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from src.media.config import MediaError, resolve_credential

from .types import AudioInput, SttOptions, SttProvider, SttResult

DEFAULT_URL = "https://api.deepgram.com/v1/listen"

_MIME = {
    "wav": "audio/wav",
    "wave": "audio/wav",
    "mp3": "audio/mp3",
    "webm": "audio/webm",
    "ogg": "audio/ogg",
}


def _input_bytes(input: AudioInput) -> bytes:
    if isinstance(input, str):
        return Path(input).read_bytes()
    if isinstance(input, bytes):
        return input
    if isinstance(input, dict):
        if "path" in input:
            return Path(str(input["path"])).read_bytes()
        if "buffer" in input:
            return bytes(input["buffer"])
        if "base64" in input:
            return base64.b64decode(input["base64"])
    raise MediaError("provider_error", "stream input unsupported by deepgram; buffer the stream first")


def _mime_for(input: AudioInput) -> str:
    encoding = ""
    if isinstance(input, dict):
        encoding = str(input.get("encoding", "") or "")
    elif isinstance(input, str):
        encoding = input.rsplit(".", 1)[-1] if "." in input else ""
    return _MIME.get(encoding.lower(), "audio/wav")


def _clamp(c: Any) -> float:
    try:
        return min(1.0, max(0.0, float(c)))
    except (TypeError, ValueError):
        return 0.9


class DeepgramSttProvider:
    id = "deepgram"

    def transcribe(self, input: AudioInput, opts: SttOptions | None = None) -> SttResult:
        opts = opts or {}
        # Credential first — raises MediaError("missing_credentials") when unset.
        api_key = resolve_credential(
            {"provider": self.id, "credentials_env": opts.get("credentials_env") or "DEEPGRAM_API_KEY"}
        )

        params = {"model": opts.get("model") or "nova-2", "smart_format": "false"}
        if opts.get("language"):
            params["language"] = str(opts["language"])
        url = f"{DEFAULT_URL}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(
            url,
            data=_input_bytes(input),
            method="POST",
            headers={"Authorization": f"Token {api_key}", "Content-Type": _mime_for(input)},
        )
        try:
            with urllib.request.urlopen(req, timeout=(opts.get("timeout_ms") or 15000) / 1000.0) as res:
                payload = json.loads(res.read().decode("utf-8"))
        except MediaError:
            raise
        except urllib.error.HTTPError as err:
            raise MediaError("provider_error", f"deepgram listen failed with HTTP {err.code}") from err
        except Exception as err:
            raise MediaError("provider_error", f"deepgram transcription failed: {err}") from err

        alt: dict[str, Any] = {}
        try:
            alt = payload["results"]["channels"][0]["alternatives"][0]
        except (KeyError, IndexError, TypeError):
            alt = {}
        words = [
            {
                "text": w.get("punctuated_word") or w.get("word") or "",
                "start_ms": round(float(w.get("start", 0)) * 1000),
                "end_ms": round(float(w.get("end", 0)) * 1000),
            }
            for w in (alt.get("words") or [])
        ]
        duration_ms: int | None
        try:
            duration_ms = round(float(payload["results"]["metadata"]["duration"]) * 1000)
        except (KeyError, TypeError, ValueError):
            duration_ms = None
        return SttResult(
            text=alt.get("transcript") or "",
            confidence=_clamp(alt.get("confidence")),
            structured={
                "language": opts.get("language"),
                "duration_ms": duration_ms,
                "words": words,
                "model": opts.get("model") or "nova-2",
            },
        )


_INSTANCE = DeepgramSttProvider()


def register() -> None:
    from .types import register_stt_provider

    register_stt_provider(_INSTANCE)
