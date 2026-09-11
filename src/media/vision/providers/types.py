# Requirement IDs: MED-01, MED-03, MED-REU-01, MED-REU-02, RES-03, GOV-MIN-04, XCUT-08
"""Vision provider abstraction + runtime registry — Python mirror of
providers/types.ts (DP-C §4.2).

Providers implement the VisionProvider protocol and register via
register_vision_provider(); the wrapper resolves get_vision_provider(
config.provider) AT CALL TIME so MED_VISION_PROVIDER env swaps need zero code
change (MED-03). A missing id returns None → wrapper raises
MediaError("unknown_provider").

Isolation (MED-REU-02): imports only src.media shared surfaces — never
stt/pdf/tts (CI grep guard, DP-C §8.1).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Protocol, TypedDict

# ImageInput variants (DP-C §4.2): {"path":..} | {"buffer":..} |
# {"base64":..,"mime":..} | {"url":..} — url fetch optional/disabled offline.
ImageInput = Dict[str, Any]

VisionOptions = Dict[str, Any]  # MediaConfig slice + generic prompt override


class VisionResult(TypedDict):
    text: str
    confidence: float
    structured: Optional[Dict[str, Any]]


class VisionProvider(Protocol):
    """One image-captioning backend.

    Implementations MUST raise on provider-side failure (network, rate limit,
    missing credentials) so RES-01 can retry/fallback (RES-REU-02); they never
    return error-bearing results for provider problems.
    """

    id: str

    def caption(self, input: ImageInput, opts: VisionOptions) -> VisionResult: ...


# ---------------------------------------------------------------------------
# Generic default prompt (MED-REU-01 / DP-C §6.2)
# ---------------------------------------------------------------------------

_DEFAULT_PROMPT_PATH = Path(__file__).resolve().parents[1] / "default-prompt.txt"
_default_prompt_cache: str | None = None


def default_prompt() -> str:
    """The checked-in, domain-free default instruction from
    src/media/vision/default-prompt.txt (single source, no persona wording).
    Used when config.vision.prompt is null and no per-call/env override exists."""
    global _default_prompt_cache
    if _default_prompt_cache is None:
        _default_prompt_cache = _DEFAULT_PROMPT_PATH.read_text(encoding="utf-8").strip()
    return _default_prompt_cache


# Registry (DP-C §4.2 provider swap without code change)
_REGISTRY: Dict[str, VisionProvider] = {}


def register_vision_provider(p: VisionProvider) -> None:
    """Register (or replace) a provider under its own id. Idempotent per id."""
    _REGISTRY[p.id] = p


def get_vision_provider(id: str) -> Optional[VisionProvider]:
    """Resolve by id at call time; None when unknown → caller raises
    MediaError("unknown_provider") per DP-C §7.2."""
    return _REGISTRY.get(id)


def list_vision_providers() -> list[str]:
    """All registered ids (diagnostics/tests only — never used for resolution)."""
    return sorted(_REGISTRY.keys())
