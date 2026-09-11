# Requirement IDs: MED-04, MED-AC-01, GOV-REU-02, GOV-MIN-04, NONGOAL-06
"""Always-available offline STT provider — Python mirror of synthetic-fixture.ts.

Reads the checked-in synthetic fixture pair:
    examples/dummy-fixtures/media/stt/sample.wav         (RIFF/WAVE PCM16)
    examples/dummy-fixtures/media/stt/transcript.json    (expected output)
and returns transcript.json verbatim — NO network, NO credentials. This is
what MED-AC-01 offline tests rely on. Fixture content is Acme Corp/widget
synthetic only (GOV-REU-02); the `synthetic` provenance flag is set by the
wrapper because this provider's id is "synthetic-fixture" (MED-04).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from .types import AudioInput, SttOptions, SttProvider, SttResult

_REPO_ROOT = Path(__file__).resolve().parents[4]
TRANSCRIPT_PATH = _REPO_ROOT / "examples" / "dummy-fixtures" / "media" / "stt" / "transcript.json"

_cache: Dict[str, Any] | None = None


def _load_transcript() -> Dict[str, Any]:
    global _cache
    if _cache is None:
        _cache = json.loads(TRANSCRIPT_PATH.read_text(encoding="utf-8"))
    return _cache


def _fixture_bytes(input: AudioInput) -> bytes | None:
    """Return raw bytes when the input references the checked-in WAV (path or
    file-like stream), so a corrupt/missing fixture surfaces as an error
    instead of silently returning canned text. None = nothing to sniff."""
    if isinstance(input, str):
        return Path(input).read_bytes()
    if isinstance(input, dict) and "path" in input:
        return Path(str(input["path"])).read_bytes()
    return None


def _assert_wav(data: bytes) -> None:
    if len(data) < 12 or data[0:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError("fixture audio is not a RIFF/WAVE file")


class SyntheticFixtureSttProvider:
    id = "synthetic-fixture"

    def transcribe(self, input: AudioInput, opts: SttOptions | None = None) -> SttResult:
        wav = _fixture_bytes(input)
        if wav is not None:
            _assert_wav(wav)
        t = _load_transcript()
        structured: Dict[str, Any] = {
            "language": t.get("language", "en"),
            "duration_ms": t.get("duration_ms", 1840),
        }
        if isinstance(t.get("words"), list):
            structured["words"] = t["words"]
        return SttResult(text=str(t.get("text", "")), confidence=0.94, structured=structured)


_INSTANCE = SyntheticFixtureSttProvider()


def register() -> None:
    from .types import register_stt_provider

    register_stt_provider(_INSTANCE)
