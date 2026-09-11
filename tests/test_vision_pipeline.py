"""DP-VISION pipeline tests."""
from __future__ import annotations

import cv2
import numpy as np

from app.contracts.schemas import VISION_SCORES_SCHEMA
from src.resilience import validate


def _check(result) -> list:
    if isinstance(result, dict):
        return result.get("errors", [])
    return list(result or [])


def _make_clip(path, frames=60, width=320, height=240, noise_seed=None):
    w = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), 30.0, (width, height))
    for i in range(frames):
        f = np.zeros((height, width, 3), np.uint8)
        cv2.rectangle(f, (i * 4 % (width - 40), 100), ((i * 4 % (width - 40)) + 30, 130), (255, 255, 255), -1)
        w.write(f)
    w.release()


def _cfg(source):
    return {
        "run_id": "t", "source": source, "backend": "baseline",
        "sample_every_n": 3, "max_frames": 60, "roi": None,
        "thresholds": {}, "synthetic": True, "replay": False,
        "evidence_prefix": "t",
    }


def _run_clip(path, cfg):
    from app.vision import analyze_frame, create_pipeline_state, get_backend, iter_frames

    backend = get_backend("baseline")
    backend.reset_state()
    state = create_pipeline_state(cfg)
    out = []
    for idx, t_ms, frame in iter_frames(path, cfg):
        out.append(analyze_frame(frame, state, cfg, backend, idx, t_ms))
    return out


def test_source_sampling(tmp_path):
    from app.vision.source import iter_frames, probe_source

    p = str(tmp_path / "clip.mp4")
    _make_clip(p)
    cfg = _cfg(p)
    got = list(iter_frames(p, cfg))
    assert probe_source(p)["kind"] == "file"
    assert len(got) == 20
    assert got[1][0] == 3
    assert got[1][1] == 100


def test_scores_validate(tmp_path):
    p = str(tmp_path / "clip.mp4")
    _make_clip(p)
    scores = _run_clip(p, _cfg(p))
    assert len(scores) > 0
    for s in scores:
        assert _check(validate(VISION_SCORES_SCHEMA, s)) == []


def test_determinism(tmp_path):
    p = str(tmp_path / "clip.mp4")
    _make_clip(p)
    a = _run_clip(p, _cfg(p))
    b = _run_clip(p, _cfg(p))
    for x, y in zip(a, b):
        x2 = dict(x); x2.pop("ops_ms", None)
        y2 = dict(y); y2.pop("ops_ms", None)
        assert x2 == y2


def test_spaghetti_clip_scores_higher(tmp_path):
    from app.vision import analyze_frame, create_pipeline_state, get_backend

    p = str(tmp_path / "orderly.mp4")
    _make_clip(p)
    orderly = _run_clip(p, _cfg(p))
    # Noisy clip: salt-and-pepper frames written directly.
    q = str(tmp_path / "noisy.mp4")
    rng = np.random.default_rng(7)
    w = cv2.VideoWriter(q, cv2.VideoWriter_fourcc(*"mp4v"), 30.0, (320, 240))
    for _ in range(60):
        f = (rng.integers(0, 256, (240, 320, 3))).astype(np.uint8)
        w.write(f)
    w.release()
    noisy = _run_clip(q, _cfg(q))
    mo = float(sum(s["spaghetti_score"] for s in orderly) / max(1, len(orderly)))
    mn = float(sum(s["spaghetti_score"] for s in noisy) / max(1, len(noisy)))
    assert mn - mo >= 0.15, (mo, mn)


def test_degrades_on_bad_frame():
    from app.vision import analyze_frame, create_pipeline_state, get_backend

    backend = get_backend("baseline")
    backend.reset_state()
    cfg = _cfg("x")
    state = create_pipeline_state(cfg)
    out = analyze_frame(None, state, cfg, backend, 0, 0)
    assert out["degraded"] is True
    assert out["confidence"] == 0.0


def test_latency_budget(tmp_path):
    import time

    from app.vision import analyze_frame, create_pipeline_state, get_backend

    p = str(tmp_path / "hd.mp4")
    w = cv2.VideoWriter(p, cv2.VideoWriter_fourcc(*"mp4v"), 30.0, (1280, 720))
    for i in range(30):
        f = np.zeros((720, 1280, 3), np.uint8)
        cv2.rectangle(f, (i * 10, 300), (i * 10 + 80, 380), (200, 170, 120), -1)
        w.write(f)
    w.release()
    cfg = {
        "run_id": "t", "source": p, "backend": "baseline",
        "sample_every_n": 1, "max_frames": 30, "roi": None,
        "thresholds": {}, "synthetic": True, "replay": False,
        "evidence_prefix": "t",
    }
    backend = get_backend("baseline")
    backend.reset_state()
    state = create_pipeline_state(cfg)
    from app.vision.source import iter_frames

    times = []
    for idx, t_ms, frame in iter_frames(p, cfg):
        f0 = time.perf_counter()
        analyze_frame(frame, state, cfg, backend, idx, t_ms)
        times.append((time.perf_counter() - f0) * 1000.0)
    assert times, "no frames measured"
    import math

    xs = sorted(times)
    p95 = xs[min(len(xs) - 1, max(0, math.ceil(0.95 * len(xs)) - 1))]
    print(f"p95_720p_ms={p95:.1f}")
    assert p95 < 400.0, p95
