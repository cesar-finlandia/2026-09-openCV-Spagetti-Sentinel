"""Golden-cache seeding — REQ-F17 offline replay.

Runs the real pipeline over every fixture once and stores the resulting VisionScores under
deterministic cache keys, so a replay run reproduces a full session with no video decoding,
no AWS and no network.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os

logger = logging.getLogger("fixtures.seed_cache")

CACHE_NAMESPACE: str = "ss.replay.v1"
"""Prefix for every key this module writes. Nothing else writes to this namespace."""


def _hash_key(readable: str) -> str:
    return hashlib.sha256(readable.encode("utf-8")).hexdigest()


def scores_key(fixture_id: str, frame_index: int) -> str:
    """Deterministic cache key: sha256 of f"{CACHE_NAMESPACE}:scores:{fixture_id}:{frame_index:06d}"."""
    return _hash_key(f"{CACHE_NAMESPACE}:scores:{fixture_id}:{frame_index:06d}")


def rationale_key(fixture_id: str, frame_index: int) -> str:
    """Deterministic cache key: sha256 of f"{CACHE_NAMESPACE}:rationale:{fixture_id}:{frame_index:06d}"."""
    return _hash_key(f"{CACHE_NAMESPACE}:rationale:{fixture_id}:{frame_index:06d}")


def seed(fixtures_dir: str = "fixtures", cache_dir: str = ".golden-cache",
         ids: tuple[str, ...] | None = None) -> dict:
    """Populate the golden cache for every fixture. Returns {fixture_id: frames_cached}."""
    from src.resilience import create_golden_cache

    from app.config.settings import load_settings
    from app.vision import analyze_frame, create_pipeline_state, get_backend, iter_frames

    cache = create_golden_cache(cache_dir)
    with open(os.path.join(fixtures_dir, "manifest.json"), encoding="utf-8") as fh:
        manifest = json.load(fh)
    backend = get_backend("baseline")
    try:
        thresholds = load_settings({}).thresholds
    except Exception:
        thresholds = {"warn": 0.45, "pause": 0.72, "confidence_floor": 0.55}
    out: dict[str, int] = {}
    for clip in manifest.get("clips", []):
        fid = clip["id"]
        if ids is not None and fid not in ids:
            continue
        cfg = {
            "run_id": f"seed-{fid}", "source": clip["path"], "backend": "baseline",
            "sample_every_n": 3, "max_frames": clip.get("frames", 300), "roi": None,
            "thresholds": thresholds, "synthetic": True, "replay": False,
            "evidence_prefix": f"seed/{fid}",
        }
        try:
            backend.reset_state()
        except Exception:
            pass
        state = create_pipeline_state(cfg)  # type: ignore[arg-type]
        count = 0
        try:
            for idx, t_ms, frame in iter_frames(clip["path"], cfg):  # type: ignore[arg-type]
                try:
                    scores = analyze_frame(frame, state, cfg, backend, idx, t_ms)  # type: ignore[arg-type]
                except Exception as err:
                    logger.warning("seed: frame %s failed (%s)", idx, type(err).__name__)
                    continue
                try:
                    cache.put(scores_key(fid, idx), scores)
                    count += 1
                except Exception as err:
                    logger.warning("seed: cache put failed (%s)", type(err).__name__)
        except Exception as err:
            logger.warning("seed: clip %s failed (%s)", fid, type(err).__name__)
        out[fid] = count
    return out


def replay_scores(fixture_id: str, cache_dir: str = ".golden-cache") -> list[dict]:
    """Read back every cached VisionScores for `fixture_id`, ordered by frame_index."""
    from src.resilience import create_golden_cache

    try:
        cache = create_golden_cache(cache_dir)
    except Exception as err:
        logger.warning("replay: cache open failed (%s)", type(err).__name__)
        return []
    out: list[dict] = []
    try:
        misses = 0
        i = 0
        while True:
            try:
                v = cache.get(scores_key(fixture_id, i))
            except Exception:
                v = None
            if v is None:
                misses += 1
                if misses >= 50:
                    break
            else:
                misses = 0
                if isinstance(v, dict):
                    out.append(v)
            i += 1
            if i > 20000:
                break
        out.sort(key=lambda d: d.get("frame_index", 0))
        return out
    except Exception as err:
        logger.warning("replay: read failed (%s)", type(err).__name__)
        return []
