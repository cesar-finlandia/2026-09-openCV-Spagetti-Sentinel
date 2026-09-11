"""DP-FIXTURES tests."""
from __future__ import annotations

import json
import os


def _mean_last(scores, n=40):
    tail = scores[-n:] if len(scores) >= n else scores
    return sum(s["spaghetti_score"] for s in tail) / max(1, len(tail))


def _run_means(clip_id):
    import json as _json

    from app.fixtures import seed as _seed  # noqa: F401 (ensure import surface)
    from app.vision import analyze_frame, create_pipeline_state, get_backend, iter_frames

    m = _json.load(open("fixtures/manifest.json"))
    clip = next(c for c in m["clips"] if c["id"] == clip_id)
    cfg = {
        "run_id": f"fx-{clip_id}", "source": clip["path"], "backend": "baseline",
        "sample_every_n": 3, "max_frames": clip.get("frames", 300), "roi": None,
        "thresholds": {"warn": 0.45, "pause": 0.72, "confidence_floor": 0.55},
        "synthetic": True, "replay": False, "evidence_prefix": f"fx/{clip_id}",
    }
    backend = get_backend("baseline")
    backend.reset_state()
    state = create_pipeline_state(cfg)
    out = []
    for idx, t_ms, frame in iter_frames(clip["path"], cfg):
        out.append(analyze_frame(frame, state, cfg, backend, idx, t_ms))
    return out


def test_manifest_shape():
    m = json.load(open("fixtures/manifest.json"))
    assert m["synthetic"] is True
    assert len(m["clips"]) == 4
    assert all(c["ok"] and os.path.getsize(c["path"]) > 0 for c in m["clips"])
    sp = next(c for c in m["clips"] if c["id"] == "spaghetti")
    assert sp["onset_frame"] == 150


def test_scenarios_separate():
    good = _run_means("good-first-layer")
    lighting = _run_means("lighting-shift")
    spag = _run_means("spaghetti")
    mg, ml, ms = _mean_last(good), _mean_last(lighting), _mean_last(spag)
    print(f"means good={mg:.3f} lighting={ml:.3f} spag={ms:.3f}")
    assert ms - mg >= 0.20, (mg, ms)
    assert abs(ml - mg) <= 0.10, (mg, ml)


def test_watermark_present():
    import cv2
    import numpy as np

    cap = cv2.VideoCapture("fixtures/clips/good-first-layer.mp4")
    ok, frame = cap.read()
    cap.release()
    assert ok
    bottom = frame[-60:, :, :]
    target = np.array([0, 230, 230], dtype=np.int16)
    dist = np.abs(bottom.astype(np.int16) - target).max(axis=2)
    assert int((dist <= 30).sum()) >= 400


def test_replay_roundtrip(tmp_path):
    from app.contracts.schemas import VISION_SCORES_SCHEMA
    from app.fixtures import replay_scores, seed
    from src.resilience import validate

    cache_dir = str(tmp_path / "cache")
    counts = seed(fixtures_dir="fixtures", cache_dir=cache_dir, ids=("good-first-layer",))
    assert counts["good-first-layer"] > 0
    back = replay_scores("good-first-layer", cache_dir=cache_dir)
    assert len(back) == counts["good-first-layer"]
    idxs = [b["frame_index"] for b in back]
    assert idxs == sorted(idxs) and len(set(idxs)) == len(idxs)

    def _check(r):
        return r.get("errors", []) if isinstance(r, dict) else list(r or [])

    for b in back:
        assert _check(validate(VISION_SCORES_SCHEMA, b)) == []
