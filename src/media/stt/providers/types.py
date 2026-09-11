# Requirement IDs: MED-01, MED-03, MED-REU-02, RES-03, GOV-MIN-04, XCUT-08
"""STT provider abstraction + runtime registry — Python mirror of providers/types.ts.

Providers implement the SttProvider protocol and register via
register_stt_provider(); the wrapper resolves get_stt_provider(config.provider)
AT CALL TIME so MED_STT_PROVIDER env swaps need zero code change (MED-03). A
missing id returns None → wrapper raises MediaError("unknown_provider").

Isolation (MED-REU-02): imports only src.media shared surfaces — never
vision/pdf/tts (CI grep guard, DP-C §8.1).
"""

from __future__ import annotations

import sys
from typing import Any, BinaryIO, Dict, Optional, Protocol, Union

if sys.version_info >= (3, 11):
    from typing import TypedDict
else:  # pragma: no cover - repo requires >=3.11
    from typing import TypedDict

# AudioInput variants (DP-C §4.1): path str | bytes | {"path":..} |
# {"base64":..} | {"stream": <binary file-like>} — optional "encoding" key.
AudioInput = Union[str, bytes, BinaryIO, Dict[str, Any]]

SttOptions = Dict[str, Any]  # MediaConfig slice + language/promptHint hints


class SttResult(TypedDict):
    text: str
    confidence: float
    structured: Optional[Dict[str, Any]]


class SttProvider(Protocol):
    """One speech-to-text backend.

    Implementations MUST raise on provider-side failure (network, rate limit,
    missing credentials) so RES-01 can retry/fallback (RES-REU-02); they never
    return error-bearing results for provider problems.
    """

    id: str

    def transcribe(self, input: AudioInput, opts: SttOptions) -> SttResult: ...


# Registry (DP-C §4.1 provider swap without code change)
_REGISTRY: Dict[str, SttProvider] = {}


def register_stt_provider(p: SttProvider) -> None:
    """Register (or replace) a provider under its own id. Idempotent per id."""
    _REGISTRY[p.id] = p


def get_stt_provider(id: str) -> Optional[SttProvider]:
    """Resolve by id at call time; None when unknown → caller raises
    MediaError("unknown_provider") per DP-C §7.2."""
    return _REGISTRY.get(id)


def list_stt_providers() -> list[str]:
    """All registered ids (diagnostics/tests only — never used for resolution)."""
    return sorted(_REGISTRY.keys())
