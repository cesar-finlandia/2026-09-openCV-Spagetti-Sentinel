# Requirement IDs: MED-04, MED-TTS-01, MED-AC-01, GOV-REU-02, GOV-MIN-04,
# NONGOAL-06
"""Always-available offline TTS provider — Python mirror of synthetic-fixture.ts.

Reads the checked-in synthetic fixture bytes:
    examples/dummy-fixtures/media/tts/sample.mp3   (~1.1 s synthetic audio)
    examples/dummy-fixtures/media/tts/sample.wav   (wav variant)
and returns them byte-for-byte — NO network, NO credentials. This is what
MED-AC-01 offline tests rely on. Fixture content is Acme Corp/widget synthetic
only (GOV-REU-02); the `synthetic` provenance flag is set by the wrapper
because this provider's id is "synthetic-fixture" (MED-04).

Request/response only: no native synthesize_stream — the wrapper polyfills
streaming by slicing these bytes (DP-C §5.1).
"""

from __future__ import annotations

from pathlib import Path

from src.media.config import MediaError

from .types import TtsInput, TtsOptions, TtsProvider, TtsResult, register_tts_provider

_REPO_ROOT = Path(__file__).resolve().parents[4]
FIXTURE_DIR = _REPO_ROOT / "examples" / "dummy-fixtures" / "media" / "tts"

_FORMAT_FILES = {
    "mp3": "sample.mp3",
    "wav": "sample.wav",
    "pcm": "sample.mp3",  # raw-tone fixture; served as-is for offline pcm tests
}

# ~1.1 s of synthetic audio per examples/dummy-fixtures/media/tts/README.md.
FIXTURE_DURATION_MS = 1120
DEFAULT_SAMPLE_RATE = 24000


def text_of(input: TtsInput) -> str:
    if isinstance(input, str):
        return input
    return str(input.get("text", ""))


class SyntheticFixtureTtsProvider:
    id = "synthetic-fixture"

    def synthesize(self, input: TtsInput, opts: TtsOptions | None = None) -> TtsResult:
        opts = opts or {}
        fmt = str(opts.get("format") or "mp3")
        name = _FORMAT_FILES.get(fmt)
        if name is None:
            # Defensive: the wrapper rejects unknown formats before this point.
            raise MediaError("provider_error", f'synthetic-fixture has no fixture for format "{fmt}"')
        path = FIXTURE_DIR / name
        try:
            audio = path.read_bytes()
        except OSError as err:  # pragma: no cover - fixture is checked in
            raise MediaError("provider_error", f"synthetic-fixture unreadable: {err}") from err
        return TtsResult(
            audio=audio,
            format=fmt,
            sample_rate=int(opts.get("sampleRate") or opts.get("sample_rate") or DEFAULT_SAMPLE_RATE),
            duration_ms=FIXTURE_DURATION_MS,
            audio_ref=f"examples/dummy-fixtures/media/tts/{name}",
        )


_INSTANCE = SyntheticFixtureTtsProvider()


def register() -> None:
    from .types import register_tts_provider as _reg

    _reg(_INSTANCE)
