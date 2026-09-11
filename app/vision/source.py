"""Frame sources — REQ-F01. Three kinds behind one iterator."""
from __future__ import annotations

import logging
import math
import os
from typing import Any, Iterator

from app.config.settings import load_settings
from app.contracts.types import RunConfig

logger = logging.getLogger("vision.source")


class SourceError(Exception):
    """Raised only by probe_source(); iter_frames() never raises."""


def _kind_of(source: str, fixtures_dir: str) -> str:
    s = source.replace("\\", "/")
    if s.startswith("rtsp://") or s.startswith("http://") or s.startswith("https://"):
        return "stream"
    fx = fixtures_dir.replace("\\", "/").rstrip("/")
    if fx and (s == fx or s.startswith(fx + "/") or s.startswith(fx)):
        return "fixture"
    return "file"


def probe_source(source: str) -> dict[str, Any]:
    """Open `source` and report {kind, frame_count, fps, width, height, opened}.

    kind is "file" | "stream" | "fixture". Raises SourceError when the source cannot be
    opened, so the API can reject a bad request before starting a run.
    """
    import cv2

    try:
        fixtures_dir = load_settings().fixtures_dir
    except Exception:
        fixtures_dir = "fixtures"
    cap = cv2.VideoCapture(source)
    try:
        if not cap.isOpened():
            raise SourceError(f"cannot open source: {source}")
        fc = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        fps = cap.get(cv2.CAP_PROP_FPS)
        w = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
        h = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
        return {
            "kind": _kind_of(source, fixtures_dir),
            "frame_count": int(fc) if fc and not math.isnan(fc) else 0,
            "fps": float(fps) if fps and not math.isnan(fps) else 0.0,
            "width": int(w),
            "height": int(h),
            "opened": True,
        }
    finally:
        try:
            cap.release()
        except Exception:
            pass


def iter_frames(source: str, cfg: RunConfig) -> Iterator[tuple[int, int, Any]]:
    """Yield (frame_index, t_ms, frame_bgr) for every SAMPLED frame of `source`.

    Sampling: yields frames where frame_index % cfg["sample_every_n"] == 0, stopping after
    cfg["max_frames"] source frames. t_ms is derived from the source's fps, so timestamps are
    reproducible across machines. Closes the capture on exhaustion and on generator close.
    """
    import cv2

    cap = cv2.VideoCapture(source)
    try:
        if not cap.isOpened():
            logger.error("vision: cannot open source %s", source)
            return
        fps = cap.get(cv2.CAP_PROP_FPS)
        try:
            fps_f = float(fps)
        except Exception:
            fps_f = 0.0
        if not fps_f or math.isnan(fps_f) or fps_f > 240:
            fps_f = 30.0
        try:
            stride = max(1, int(cfg.get("sample_every_n", 1)))
        except Exception:
            stride = 1
        try:
            limit = max(1, int(cfg.get("max_frames", 900)))
        except Exception:
            limit = 900
        i = 0
        while True:
            ok, frame = cap.read()
            if not ok or i >= limit:
                break
            if i % stride == 0:
                t_ms = int(round(i * 1000.0 / fps_f))
                yield (i, t_ms, frame)
            i += 1
    finally:
        try:
            cap.release()
        except Exception:
            pass
