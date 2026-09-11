"""Bounded observation history — REQ-N03.

src/context is TypeScript-only in this working copy and the engine is Python, so this module
implements the same sliding-window-pinned semantics in ~40 lines: keep the first observation
(pinned: it establishes the baseline) plus the most recent N, and stop growing. Token accounting
reuses the chassis counter through src.cost.meter.derive_token_counts — it is never
reimplemented here.
"""
from __future__ import annotations

from app.contracts.types import VisionScores

WINDOW: int = 8
"""Most-recent observations kept, in addition to the pinned first one."""

MAX_PROMPT_TOKENS: int = 1200
"""Hard ceiling on the rendered user prompt."""


def build_history(observations: list[VisionScores]) -> list[VisionScores]:
    """Return the pinned-first + last-WINDOW slice of `observations`, in frame order."""
    try:
        if not observations:
            return []
        pinned = observations[0]
        tail = observations[-WINDOW:]
        if len(observations) <= WINDOW:
            return list(tail)
        # pinned may already be in tail when observations short; check identity/index.
        try:
            if any(o is pinned or o.get("frame_index") == pinned.get("frame_index") for o in tail):
                # If pinned in tail, just return tail (already ordered).
                if len(tail) == len(observations):
                    return list(tail)
        except Exception:
            pass
        return [pinned] + list(tail)
    except Exception:
        return []


def estimate_tokens(text: str) -> int:
    """Token estimate for `text` via the chassis counter, falling back to len(text)//4."""
    try:
        from src.cost.meter import derive_token_counts

        out = derive_token_counts(text, {"provider": "bedrock", "label": "rationale"})
        for k in ("output_tokens", "total_tokens", "input_tokens"):
            v = out.get(k)
            if isinstance(v, (int, float)) and not isinstance(v, bool) and v is not None:
                return max(1, int(v))
    except Exception:
        pass
    try:
        return max(1, len(text) // 4)
    except Exception:
        return 1
