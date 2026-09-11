"""DP-AGENT policy tests — MT-6 / REQ-F06."""
from __future__ import annotations

import copy


def _scores(**kw):
    base = {"frame_index": 0, "t_ms": 0, "first_layer_coverage": 0.90,
            "edge_regularity": 0.60, "motion_energy": 0.10, "texture_disorder": 0.10,
            "spaghetti_score": 0.10, "confidence": 0.90, "roi": [0, 0, 10, 10],
            "backend": "baseline", "ops_ms": {}, "degraded": False}
    base.update(kw)
    return base


def _cfg():
    return {"run_id": "r", "source": "x", "backend": "baseline", "sample_every_n": 3,
            "max_frames": 300, "roi": None,
            "thresholds": {"warn": 0.45, "pause": 0.72, "confidence_floor": 0.55},
            "synthetic": True, "replay": False, "evidence_prefix": "r"}


def _check(result) -> list:
    return result.get("errors", []) if isinstance(result, dict) else list(result or [])


def test_purity():
    from app.agent.policy import decide

    s = _scores(spaghetti_score=0.5)
    h = [_scores(spaghetti_score=0.1)]
    cfg = _cfg()
    first = decide(s, h, cfg)
    for _ in range(200):
        assert decide(copy.deepcopy(s), copy.deepcopy(h), cfg) == first
    assert s["spaghetti_score"] == 0.5


def test_threshold_flip():
    from app.agent.policy import SUSTAIN_FRAMES, decide

    cfg = _cfg()
    pause = cfg["thresholds"]["pause"]
    low = [_scores(frame_index=i, spaghetti_score=pause - 0.01, confidence=0.9)
           for i in range(SUSTAIN_FRAMES)]
    high = [_scores(frame_index=i, spaghetti_score=pause + 0.01, confidence=0.9,
                    first_layer_coverage=0.9, edge_regularity=0.6)
            for i in range(SUSTAIN_FRAMES)]
    assert decide(low[-1], low[:-1], cfg)["action"] != "request_pause_approval"
    assert decide(high[-1], high[:-1], cfg)["action"] == "request_pause_approval"


def test_low_confidence_suppresses():
    from app.agent.policy import decide

    s = _scores(spaghetti_score=0.95, confidence=0.10)
    d = decide(s, [_scores(spaghetti_score=0.95, confidence=0.10) for _ in range(3)], _cfg())
    assert (d["action"], d["reason_code"]) == ("continue", "low_confidence")


def test_degraded_frame_never_escalates():
    from app.agent.policy import decide

    s = _scores(spaghetti_score=1.0, confidence=1.0, degraded=True)
    d = decide(s, [], _cfg())
    assert d["action"] == "continue"


def test_single_spike_does_not_pause():
    from app.agent.policy import decide

    cfg = _cfg()
    hist = [_scores(frame_index=i, spaghetti_score=0.05) for i in range(3)]
    spike = _scores(frame_index=9, spaghetti_score=0.95, first_layer_coverage=0.9)
    assert decide(spike, hist, cfg)["action"] == "capture_evidence"


def test_first_layer_shift():
    from app.agent.policy import decide

    s = _scores(first_layer_coverage=0.40, confidence=0.9, spaghetti_score=0.1)
    d = decide(s, [], _cfg())
    assert (d["action"], d["reason_code"]) == ("capture_evidence", "first_layer_shift")


def test_every_decision_validates():
    from src.resilience import validate

    from app.agent.policy import decide
    from app.contracts.schemas import AGENT_DECISION_SCHEMA

    cfg = _cfg()
    cases = [_scores(spaghetti_score=v) for v in (0.05, 0.5, 0.8, 0.95)]
    for s in cases:
        d = decide(s, [], cfg)
        assert _check(validate(AGENT_DECISION_SCHEMA, d)) == [], d


def test_reason_codes_closed():
    from app.agent.policy import REASON_CODES, decide

    cfg = _cfg()
    for v in (0.0, 0.5, 0.73, 0.95):
        d = decide(_scores(spaghetti_score=v), [], cfg)
        assert d["reason_code"] in REASON_CODES
