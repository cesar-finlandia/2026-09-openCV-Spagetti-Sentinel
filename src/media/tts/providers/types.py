# Requirement IDs: MED-01, MED-TTS-01, MED-TTS-02, MED-REU-02, RES-03,
# GOV-MIN-04, XCUT-08
"""TTS provider abstraction + runtime registry — Python mirror of types.ts (DP-C §4.4).

Providers implement the TtsProvider protocol and register via
register_tts_provider(); the wrapper resolves get_tts_provider(config.provider)
AT CALL TIME so MED_TTS_PROVIDER env swaps need zero code change (MED-03). A
missing id returns None → wrapper raises MediaError("unknown_provider").

synthesize_stream is OPTIONAL: request/response providers omit it and the
wrapper polyfills streaming by slicing synthesized bytes into 4KB base64
chunks (DP-C §5.1); native-streaming providers implement it and the wrapper
delegates verbatim.

NONGOAL-04: voice is a provider voice-id passthrough ("alloy"); no
persona/tone/dialogue-policy logic lives anywhere under src/media/tts.

Isolation (MED-REU-02): imports only src.media shared surfaces — never
stt/vision/pdf (CI grep guard, DP-C §8.1).
"""

from __future__ import annotations

from typing import Any, AsyncIterator, Dict, Optional, Protocol, TypedDict, Union

# Text to synthesize: bare str (1..5000 chars) or {"text": ..., "voice": ...}.
TtsInput = Union[str, Dict[str, Any]]

TtsOptions = Dict[str, Any]  # MediaConfig slice + voice/format/sampleRate/signal

TtsFormat = str  # "mp3" | "wav" | "pcm"; anything else → error unsupported_format


class TtsChunk(TypedDict):
    """One incremental audio chunk yielded by synthesize_stream (MED-TTS-01)."""

    audio_chunk: str  # base64-encoded partial audio
    delta_text: str  # text span covered; "" when unavailable (polyfill)
    index: int
    is_final: bool
    latency_ms: Optional[int]  # measured ms to this chunk (MED-TTS-03)


class TtsResult(TypedDict):
    """Normalized non-streaming provider result."""

    audio: bytes
    format: str
    sample_rate: int
    duration_ms: Optional[int]
    audio_ref: Optional[str]  # fixture path; None → inline base64


class TtsProvider(Protocol):
    """One text-to-speech backend.

    Implementations MUST raise on provider-side failure (network, rate limit,
    missing credentials) so RES-01 can retry/fallback (RES-REU-02); they never
    return error-bearing results for provider problems.
    """

    id: str

    def synthesize(self, input: TtsInput, opts: TtsOptions) -> TtsResult: ...

    def synthesize_stream(self, input: TtsInput, opts: TtsOptions) -> AsyncIterator[TtsChunk]: ...  # optional — absent() → wrapper polyfills


def has_native_stream(provider: TtsProvider) -> bool:
    """True when the provider implements its own synthesize_stream."""
    stream = getattr(provider, "synthesize_stream", None)
    return callable(stream) and getattr(stream, "__isabstractmethod__", False) is not True


# Registry (DP-C §4.4 provider swap without code change)
_REGISTRY: Dict[str, TtsProvider] = {}


def register_tts_provider(p: TtsProvider) -> None:
    """Register (or replace) a provider under its own id. Idempotent per id."""
    _REGISTRY[p.id] = p


def get_tts_provider(id: str) -> Optional[TtsProvider]:
    """Resolve by id at call time; None when unknown → caller raises
    MediaError("unknown_provider") per DP-C §7.2."""
    return _REGISTRY.get(id)


def list_tts_providers() -> list[str]:
    """All registered ids (diagnostics/tests only — never used for resolution)."""
    return sorted(_REGISTRY.keys())
