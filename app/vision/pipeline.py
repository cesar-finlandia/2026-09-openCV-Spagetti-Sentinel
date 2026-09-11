"""The OpenCV 5 analysis pipeline — REQ-F02/F04.

analyze_frame() is pure with respect to its inputs plus the explicit PipelineState it is
handed: the same frames in the same order always produce the same scores (R7). No randomness,
no wall-clock dependence in any score (only in ops_ms).
"""
from __future__ import annotations

import logging
import math
from typing import Any

from app.contracts.types import RunConfig, VisionScores
from app.vision.backend import VisionBackend
from app.vision.ops import OP_NAMES, timed

logger = logging.getLogger("vision.pipeline")

WORK_WIDTH: int = 960
WORK_HEIGHT: int = 540
"""Every frame is resized to this working resolution before analysis."""

HISTORY_LEN: int = 12
"""Sliding window length, in sampled frames, for motion and texture differencing."""


def clamp01(x: Any) -> float:
    try:
        return min(1.0, max(0.0, float(x)))
    except Exception:
        return 0.0


class PipelineState:
    """Mutable per-run state: the background model, the ROI, and the sliding window."""

    def __init__(self) -> None:
        self.roi: list[int] | None = None
        self.frames_seen: int = 0
        self.gray_history: list[Any] = []
        self.coverage_history: list[float] = []
        self.baseline_coverage: float | None = None
        self.ref_gray: Any = None


def create_pipeline_state(cfg: RunConfig) -> PipelineState:
    """Fresh state for one run. Seeds roi from cfg["roi"] (None = auto-detect on frame 0)."""
    st = PipelineState()
    try:
        r = cfg.get("roi")
        st.roi = list(r) if r else None
    except Exception:
        st.roi = None
    st.frames_seen = 0
    st.gray_history = []
    st.coverage_history = []
    st.baseline_coverage = None
    st.ref_gray = None
    return st


def detect_roi(backend: VisionBackend, gray: Any) -> list[int]:
    """Auto-detect the print-bed ROI as [x, y, w, h]."""
    import numpy as np

    try:
        h, w = gray.shape[:2]
        edges = backend.sobel(gray, 1, 1, 3)
        mag = np.abs(np.asarray(edges, dtype=np.float64))
        col = mag.sum(axis=0)
        row = mag.sum(axis=1)
        x, ww = _energy_span(col, w)
        y, hh = _energy_span(row, h)
        # Pad 4% each side.
        px = int(0.04 * w)
        py = int(0.04 * h)
        x0 = max(0, x - px)
        y0 = max(0, y - py)
        x1 = min(w, x + ww + px)
        y1 = min(h, y + hh + py)
        ww2 = x1 - x0
        hh2 = y1 - y0
        if ww2 < 0.25 * w or hh2 < 0.25 * h:
            return [int(0.15 * w), int(0.15 * h), int(0.70 * w), int(0.70 * h)]
        return [int(x0), int(y0), int(ww2), int(hh2)]
    except Exception:
        try:
            h, w = gray.shape[:2]
            return [int(0.15 * w), int(0.15 * h), int(0.70 * w), int(0.70 * h)]
        except Exception:
            return [0, 0, 0, 0]


def _energy_span(proj: Any, n: int) -> tuple[int, int]:
    import numpy as np

    arr = np.asarray(proj, dtype=np.float64).ravel()
    total = float(arr.sum())
    if total <= 0 or n <= 0:
        return (0, n)
    target = 0.80 * total
    peak = int(np.argmax(arr))
    lo = peak
    hi = peak
    acc = float(arr[peak])
    while acc < target and (lo > 0 or hi < n - 1):
        left = float(arr[lo - 1]) if lo > 0 else -1.0
        right = float(arr[hi + 1]) if hi < n - 1 else -1.0
        if right >= left and hi < n - 1:
            hi += 1
            acc += float(arr[hi])
        elif lo > 0:
            lo -= 1
            acc += float(arr[lo])
        else:
            break
    return (lo, hi - lo + 1)


def analyze_frame(frame: Any, state: PipelineState, cfg: RunConfig,
                  backend: VisionBackend, frame_index: int, t_ms: int) -> VisionScores:
    """Run the full OpenCV 5 pipeline over one frame and return a complete VisionScores."""
    import numpy as np

    ops: dict[str, float] = {name: 0.0 for name in OP_NAMES}
    try:
        small = timed("resize", ops, lambda: backend.resize(frame, WORK_WIDTH, WORK_HEIGHT))
        gray = timed("cvt_gray", ops, lambda: backend.cvt_gray(small))
        blur = timed("gaussian_blur", ops, lambda: backend.gaussian_blur(gray, 5, 1.2))
        # Stabilisation.
        if state.frames_seen == 0:
            state.ref_gray = blur
        else:
            try:
                import cv2

                a = np.asarray(state.ref_gray, dtype=np.float32)
                b = np.asarray(blur, dtype=np.float32)
                (dx, dy), _resp = cv2.phaseCorrelate(a, b)
                if abs(dx) <= 24 and abs(dy) <= 24:
                    import numpy as _np

                    M = _np.array([[1, 0, -dx], [0, 1, -dy]], dtype=_np.float32)
                    cur = blur
                    blur = timed("warp_affine", ops,
                                 lambda: backend.warp_affine(cur, M, WORK_WIDTH, WORK_HEIGHT))
                else:
                    ops["warp_affine"] += 0.0
            except Exception:
                ops["warp_affine"] += 0.0
        # ROI.
        if state.roi is None:
            state.roi = detect_roi(backend, blur)
        x, y, w, h = (int(v) for v in state.roi)
        H, W = blur.shape[:2]
        x = max(0, min(x, W - 1)); y = max(0, min(y, H - 1))
        w = max(1, min(w, W - x)); h = max(1, min(h, H - y))
        state.roi = [x, y, w, h]
        roi_gray = np.asarray(blur)[y:y + h, x:x + w]
        # Background subtraction + mask.
        fg = timed("bg_subtract", ops, lambda: backend.bg_subtract(roi_gray))
        mask = timed("threshold", ops, lambda: backend.threshold(fg, 200, 255))
        cur_m = mask
        mask = timed("morphology", ops, lambda: backend.morphology(cur_m, "open", 3))
        cur_m2 = mask
        mask = timed("morphology", ops, lambda: backend.morphology(cur_m2, "close", 5))
        # Coverage.
        coverage_raw = float(np.count_nonzero(np.asarray(roi_gray) > 40)) / max(1, roi_gray.size)
        if state.frames_seen == 0:
            state.baseline_coverage = coverage_raw
        base = state.baseline_coverage or coverage_raw or 1e-6
        first_layer_coverage = clamp01(min(1.0, coverage_raw / max(1e-6, base)))
        # Edge regularity.
        gx = timed("sobel", ops, lambda: backend.sobel(roi_gray, 1, 0, 3))
        gy = timed("sobel", ops, lambda: backend.sobel(roi_gray, 0, 1, 3))
        gx_a = np.asarray(gx, dtype=np.float64)
        gy_a = np.asarray(gy, dtype=np.float64)
        mag = np.hypot(gx_a, gy_a)
        gated = mag > 20
        if int(np.count_nonzero(gated)) < 200:
            edge_regularity = 0.5
        else:
            ang = np.arctan2(gy_a[gated], gx_a[gated])
            hist, _ = np.histogram(ang, bins=36, range=(-math.pi, math.pi))
            total_h = float(hist.sum())
            if total_h <= 0:
                edge_regularity = 0.5
            else:
                p = hist.astype(np.float64) / total_h
                nz = p[p > 0]
                ent = float(-(nz * np.log(nz)).sum())
                edge_regularity = clamp01(1.0 - ent / math.log(36))
        # Contours.
        import cv2

        contours = timed("find_contours", ops, lambda: backend.find_contours(mask))
        blob_count = 0
        for c in contours:
            try:
                if float(cv2.contourArea(c)) >= 40.0:
                    blob_count += 1
            except Exception:
                continue
        # Motion energy.
        if not state.gray_history:
            motion_energy = 0.0
        else:
            prev = state.gray_history[-1]
            try:
                diff = cv2.absdiff(np.asarray(roi_gray), np.asarray(prev))
                motion_energy = clamp01(float(np.mean(diff)) / 24.0)
            except Exception:
                motion_energy = 0.0
        # Texture disorder.
        state.gray_history.append(np.asarray(roi_gray).copy())
        if len(state.gray_history) > HISTORY_LEN:
            state.gray_history = state.gray_history[-HISTORY_LEN:]
        if len(state.gray_history) < 3:
            texture_disorder = 0.0
        else:
            diffs = []
            for a, b in zip(state.gray_history[:-1], state.gray_history[1:]):
                try:
                    diffs.append(float(np.mean(cv2.absdiff(np.asarray(a), np.asarray(b)))))
                except Exception:
                    diffs.append(0.0)
            acc = float(sum(diffs) / max(1, len(diffs)))
            texture_disorder = clamp01((acc / 18.0) * (1.0 + min(1.0, blob_count / 25.0)) / 2.0)
        # Scores.
        spaghetti_score = clamp01(
            0.40 * texture_disorder
            + 0.30 * (1.0 - edge_regularity)
            + 0.20 * motion_energy
            + 0.10 * clamp01((0.85 - first_layer_coverage) / 0.85)
        )
        warmup = min(1.0, (state.frames_seen + 1) / 8.0)
        try:
            mean_gray = float(np.mean(np.asarray(roi_gray)))
        except Exception:
            mean_gray = 128.0
        lighting = 1.0 - clamp01(abs(mean_gray - 128.0) / 128.0) * 0.5
        if spaghetti_score > 0.3:
            support = 0.6 + 0.4 * min(1.0, blob_count / 5.0)
        else:
            support = 1.0
        confidence = clamp01(warmup * lighting * support)
        state.frames_seen += 1
        state.coverage_history.append(float(first_layer_coverage))
        if len(state.coverage_history) > HISTORY_LEN:
            state.coverage_history = state.coverage_history[-HISTORY_LEN:]
        return {
            "frame_index": int(frame_index), "t_ms": int(t_ms),
            "first_layer_coverage": round(float(first_layer_coverage), 4),
            "edge_regularity": round(float(edge_regularity), 4),
            "motion_energy": round(float(motion_energy), 4),
            "texture_disorder": round(float(texture_disorder), 4),
            "spaghetti_score": round(float(spaghetti_score), 4),
            "confidence": round(float(confidence), 4),
            "roi": [int(x), int(y), int(w), int(h)],
            "backend": backend.name,
            "ops_ms": {k: round(float(v), 3) for k, v in ops.items()},
            "degraded": False,
        }
    except Exception as err:
        logger.warning("vision: frame %s failed (%s); degrading", frame_index, type(err).__name__)
        try:
            roi = list(state.roi) if state.roi else [0, 0, 0, 0]
        except Exception:
            roi = [0, 0, 0, 0]
        try:
            bname = backend.name
        except Exception:
            bname = "baseline"
        return {
            "frame_index": int(frame_index), "t_ms": int(t_ms),
            "first_layer_coverage": 0.0, "edge_regularity": 0.0, "motion_energy": 0.0,
            "texture_disorder": 0.0, "spaghetti_score": 0.0, "confidence": 0.0,
            "roi": [int(v) for v in roi],
            "backend": bname,
            "ops_ms": {k: round(float(v), 3) for k, v in ops.items()},
            "degraded": True,
        }
