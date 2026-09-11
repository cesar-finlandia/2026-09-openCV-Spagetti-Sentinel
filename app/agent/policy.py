"""decide() — the deterministic policy. REQ-F06 / MT-6.

BINDING: this function's only inputs are the vision JSON, the observation history and the run
config's thresholds. It calls no model, reads no clock, touches no I/O and uses no randomness.
The same VisionScores and the same history always produce the same AgentDecision. This purity
IS the Agentic Vision qualifying condition.
"""
from __future__ import annotations

from app.contracts.types import AgentDecision, ActionName, RunConfig, VisionScores

REASON_CODES: tuple[str, ...] = (
    "nominal",
    "low_confidence",
    "texture_rising",
    "first_layer_shift",
    "spaghetti_confirmed",
    "degraded_frame",
)

SUSTAIN_FRAMES: int = 3
"""A pause is requested only when the score has been above the pause threshold for this many
consecutive sampled frames."""

COVERAGE_DROP_THRESHOLD: float = 0.55
"""first_layer_coverage below this, with confidence above the floor, is a first-layer shift."""


def _decision(scores: VisionScores, action: ActionName, reason_code: str,
              threshold: float, requires_human: bool) -> AgentDecision:
    return {
        "frame_index": int(scores.get("frame_index", 0)),
        "t_ms": int(scores.get("t_ms", 0)),
        "action": action,
        "reason_code": reason_code,
        "spaghetti_score": float(scores.get("spaghetti_score", 0.0)),
        "confidence": float(scores.get("confidence", 0.0)),
        "threshold": float(threshold),
        "requires_human": bool(requires_human),
        "rationale": "",
        "checklist": [],
        "evidence_uri": None,
        "rationale_source": "fallback",
        "degraded": bool(scores.get("degraded", False)),
    }


def decide(scores: VisionScores, history: list[VisionScores], cfg: RunConfig) -> AgentDecision:
    """Select exactly one action. Pure; never raises."""
    try:
        th = cfg.get("thresholds", {}) or {}
        warn = float(th.get("warn", 0.45))
        pause = float(th.get("pause", 0.72))
        floor = float(th.get("confidence_floor", 0.55))
        s = float(scores.get("spaghetti_score", 0.0))
        c = float(scores.get("confidence", 0.0))
        # 3. Degraded frame.
        if scores.get("degraded"):
            return _decision(scores, "continue", "degraded_frame", warn, False)
        # 4. Low confidence.
        if c < floor:
            return _decision(scores, "continue", "low_confidence", floor, False)
        # 5. Sustained failure.
        recent = list((history or [])[-(SUSTAIN_FRAMES - 1):]) + [scores]
        if len(recent) == SUSTAIN_FRAMES and all(
            float(h.get("spaghetti_score", 0.0)) >= pause
            and float(h.get("confidence", 0.0)) >= floor for h in recent
        ):
            return _decision(scores, "request_pause_approval", "spaghetti_confirmed", pause, True)
        # 6. First-layer shift.
        try:
            cov = float(scores.get("first_layer_coverage", 1.0))
        except Exception:
            cov = 1.0
        if cov < COVERAGE_DROP_THRESHOLD and c >= floor:
            return _decision(scores, "capture_evidence", "first_layer_shift",
                             COVERAGE_DROP_THRESHOLD, False)
        # 7. Rising texture.
        if s >= warn:
            return _decision(scores, "capture_evidence", "texture_rising", warn, False)
        # 8. Drifting edge regularity.
        try:
            er = float(scores.get("edge_regularity", 1.0))
        except Exception:
            er = 1.0
        if er < 0.30 and s >= warn * 0.6:
            return _decision(scores, "nudge_parameters", "texture_rising", warn * 0.6, False)
        # 9. Otherwise.
        return _decision(scores, "continue", "nominal", warn, False)
    except Exception:
        try:
            warn = float((cfg.get("thresholds", {}) or {}).get("warn", 0.45))
        except Exception:
            warn = 0.45
        return _decision(scores, "continue", "degraded_frame", warn, False)
