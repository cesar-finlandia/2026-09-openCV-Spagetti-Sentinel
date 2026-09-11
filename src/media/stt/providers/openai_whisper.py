# Requirement IDs: MED-03, MED-RES-01, GOV-MIN-04, GOV-RES-02, XCUT-08
"""openai-whisper STT provider — Python mirror of openai-whisper.ts.

Optional-dep style (GOV-MIN-04): the `openai` SDK is imported lazily on first
call; an absent SDK or credential surfaces as a RAISED MediaError at call time
so RES-01 can retry/fallback — never a startup crash. The credential VALUE is
read via resolve_credential() using only the env var NAME held in
credentials_env (GOV-RES-02 indirection). Model default: whisper-1.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.media.config import MediaError, resolve_credential

from .types import AudioInput, SttOptions, SttProvider, SttResult


def _client(api_key: str) -> Any:
    try:
        import openai  # optional peer dependency — lazy (GOV-MIN-04)
    except ImportError as err:  # pragma: no cover - exercised only without SDK
        raise MediaError("provider_error", f"openai SDK unavailable: {err}") from err
    return openai.OpenAI(api_key=api_key)


def _upload_payload(input: AudioInput) -> tuple[bytes, str]:
    """(bytes, filename) pair for the transcription upload."""
    if isinstance(input, str):
        p = Path(input)
        return p.read_bytes(), p.name or "audio.wav"
    if isinstance(input, bytes):
        return input, "audio.wav"
    if isinstance(input, dict):
        if "path" in input:
            p = Path(str(input["path"]))
            return p.read_bytes(), p.name or "audio.wav"
        if "buffer" in input:
            return bytes(input["buffer"]), "audio.wav"
        if "base64" in input:
            import base64

            return base64.b64decode(input["base64"]), "audio.wav"
    raise MediaError("provider_error", "stream input unsupported by openai-whisper; buffer the stream first")


class OpenaiWhisperSttProvider:
    id = "openai-whisper"

    def transcribe(self, input: AudioInput, opts: SttOptions | None = None) -> SttResult:
        opts = opts or {}
        # Credential first — call-time check (GOV-RES-02); raises
        # MediaError("missing_credentials") when the named env var is unset.
        api_key = resolve_credential(
            {"provider": self.id, "credentials_env": opts.get("credentials_env") or "OPENAI_API_KEY"}
        )
        data, filename = _upload_payload(input)
        model = opts.get("model") or "whisper-1"
        try:
            client = _client(api_key)
            kwargs: dict[str, Any] = {"model": model}
            if opts.get("language"):
                kwargs["language"] = opts["language"]
            if opts.get("promptHint"):
                kwargs["prompt"] = opts["promptHint"]
            result = client.audio.transcriptions.create(
                file=(filename, data), **kwargs
            )
            text = getattr(result, "text", "") or ""
        except MediaError:
            raise
        except Exception as err:
            raise MediaError("provider_error", f"openai-whisper transcription failed: {err}") from err
        return SttResult(
            text=text,
            confidence=0.9,  # whisper reports no confidence; neutral default
            structured={
                "language": opts.get("language"),
                "duration_ms": None,
                "words": [],
                "model": model,
            },
        )


_INSTANCE = OpenaiWhisperSttProvider()


def register() -> None:
    from .types import register_stt_provider

    register_stt_provider(_INSTANCE)
