"""DP-FOUNDATION contract tests."""
from __future__ import annotations

import io
import json
import os
from contextlib import redirect_stderr


def _check(result) -> list:
    # Chassis validate(schema, data) -> {valid, errors}; accept list form too.
    if isinstance(result, dict):
        return result.get("errors", [])
    return list(result or [])


def test_opencv_major_version_is_5():
    try:
        import cv2
    except Exception:
        raise AssertionError("OpenCV is not installed — MT-1 requires OpenCV 5")
    major = int(str(cv2.__version__).split(".")[0])
    assert major == 5, (
        f"OpenCV major version is {major}, but the competition mandates OpenCV 5 (brief §4.1 MT-1)"
    )


def test_steps_json_matches_python():
    import json as _json

    from app.contracts.steps import ALL_STEPS

    m = _json.load(open("app/contracts/steps.json"))["steps"]
    assert list(ALL_STEPS) == m


def _example_scores(backend="baseline"):
    return {
        "frame_index": 0, "t_ms": 0, "first_layer_coverage": 0.9,
        "edge_regularity": 0.8, "motion_energy": 0.1, "texture_disorder": 0.1,
        "spaghetti_score": 0.05, "confidence": 0.9, "roi": [0, 0, 64, 64],
        "backend": backend, "ops_ms": {"resize": 1.0}, "degraded": False,
    }


def _example_decision():
    return {
        "frame_index": 0, "t_ms": 0, "action": "continue", "reason_code": "nominal",
        "spaghetti_score": 0.05, "confidence": 0.9, "threshold": 0.45,
        "requires_human": False, "rationale": "", "checklist": [],
        "evidence_uri": None, "rationale_source": "fallback", "degraded": False,
    }


def _example_summary():
    return {
        "run_id": "r1", "backend": "baseline", "frames_processed": 10,
        "frames_sampled": 4, "wall_ms": 100, "fps": 40.0, "p50_frame_ms": 2.0,
        "p95_frame_ms": 3.0, "decisions": [], "first_alert_frame": None,
        "first_alert_t_ms": None, "pause_recommended": False, "approvals": [],
        "evidence_uris": [], "degraded": False, "synthetic": True,
        "build_marker": "dev",
    }


def test_schemas_validate_examples():
    from src.resilience import validate

    from app.contracts.schemas import (
        AGENT_DECISION_SCHEMA,
        RUN_SUMMARY_SCHEMA,
        VISION_SCORES_SCHEMA,
    )

    good = _example_scores()
    bad = dict(good)
    bad["spaghetti_score"] = 1.7
    assert _check(validate(VISION_SCORES_SCHEMA, good)) == []
    assert len(_check(validate(VISION_SCORES_SCHEMA, bad))) > 0
    assert _check(validate(AGENT_DECISION_SCHEMA, _example_decision())) == []
    assert _check(validate(RUN_SUMMARY_SCHEMA, _example_summary())) == []


def test_settings_defaults_and_degradation():
    from app.config.settings import load_settings

    buf = io.StringIO()
    with redirect_stderr(buf):
        s = load_settings({})
        d = load_settings(
            {
                "SS_MAX_FRAMES": "abc",
                "SS_BACKEND": "weird",
                "SS_WARN_THRESHOLD": "0.9",
                "SS_PAUSE_THRESHOLD": "0.2",
            }
        )
    assert (s.backend, s.max_frames, s.thresholds["pause"], s.s3_bucket) == (
        "cool", 900, 0.72, None,
    )
    assert (d.backend, d.max_frames, d.thresholds["warn"], d.thresholds["pause"]) == (
        "cool", 900, 0.45, 0.72,
    )
