"""Build identity — REQ-F16."""
from __future__ import annotations

import os
import platform
import re

import app


def _resolve_marker() -> str:
    v = os.environ.get("BUILD_MARKER", "").strip()
    if v:
        marker = v
    elif os.path.exists("build-marker.txt"):
        try:
            with open("build-marker.txt", encoding="utf-8") as fh:
                marker = fh.readline().strip()
        except Exception:
            marker = "dev"
        if not marker:
            marker = "dev"
    else:
        marker = "dev"
    marker = re.sub(r"[^A-Za-z0-9._-]", "", marker)[:64] or "dev"
    return marker


BUILD_MARKER: str = _resolve_marker()


def build_info() -> dict:
    """{"build_marker": …, "app_version": …, "opencv_version": …, "cool_version": …,
    "arch": …, "backend": …, "python": …}. Contains no credential and no bucket key."""
    try:
        import cv2

        ocv = cv2.__version__
    except Exception:
        ocv = "unknown"
    try:
        from app.vision.backend import cool_version

        cool = cool_version()
    except Exception:
        cool = None
    try:
        from app.config.settings import load_settings

        backend = load_settings().backend
    except Exception:
        backend = "cool"
    return {
        "build_marker": BUILD_MARKER,
        "app_version": getattr(app, "__version__", "1.0.0"),
        "opencv_version": ocv,
        "cool_version": cool,
        "arch": platform.machine(),
        "backend": backend,
        "python": platform.python_version(),
    }
