"""VisionBackend — the ONLY place OpenCV operations are invoked (REQ-F03).

Two implementations: CoolBackend (COOL build, Arm/Graviton) and BaselineBackend (stock
OpenCV 5). Selection is a runtime probe, never an import-time hard dependency: if the COOL
build is not present, get_backend("cool") warns once and returns the baseline backend with
cool_available=False, so a missing COOL never takes the demo down (R1).
"""
from __future__ import annotations

import importlib
import logging
import platform
from typing import Any, Protocol

from app.contracts.types import BackendInfo, BackendName

logger = logging.getLogger("vision.backend")

COOL_MODULE_CANDIDATES: tuple[str, ...] = ("cv2.cool", "cool", "opencv_cool")
"""Import paths probed, in order, to detect the COOL build. First hit wins."""

_WARNED_ONCE = False


class VisionBackend(Protocol):
    """Structural interface both backends satisfy. `Mat` values are numpy ndarrays."""

    name: BackendName

    def resize(self, src: Any, width: int, height: int) -> Any: ...
    def cvt_gray(self, src: Any) -> Any: ...
    def gaussian_blur(self, src: Any, ksize: int, sigma: float) -> Any: ...
    def bg_subtract(self, src: Any) -> Any: ...
    def threshold(self, src: Any, thresh: int, maxval: int) -> Any: ...
    def morphology(self, src: Any, op: str, ksize: int) -> Any: ...
    def warp_affine(self, src: Any, matrix: Any, width: int, height: int) -> Any: ...
    def sobel(self, src: Any, dx: int, dy: int, ksize: int) -> Any: ...
    def find_contours(self, src: Any) -> list[Any]: ...
    def reset_state(self) -> None: ...


def _probe_cool_module() -> Any | None:
    for name in COOL_MODULE_CANDIDATES:
        try:
            mod = importlib.import_module(name)
        except ImportError:
            continue
        except Exception:
            continue
        if any(hasattr(mod, a) for a in ("__version__", "version", "COOL_VERSION")):
            return mod
    return None


def cool_available() -> bool:
    """True iff one of COOL_MODULE_CANDIDATES imports AND exposes a version attribute."""
    return _probe_cool_module() is not None


def cool_version() -> str | None:
    """The COOL build's version string, or None when COOL is not present."""
    mod = _probe_cool_module()
    if mod is None:
        return None
    for attr in ("__version__", "version", "COOL_VERSION"):
        if hasattr(mod, attr):
            try:
                return str(getattr(mod, attr))
            except Exception:
                return None
    return None


class BaselineBackend:
    name: BackendName = "baseline"

    def __init__(self) -> None:
        import cv2

        self._mog = cv2.createBackgroundSubtractorMOG2(
            history=200, varThreshold=24, detectShadows=False
        )

    def resize(self, src: Any, width: int, height: int) -> Any:
        import cv2

        return cv2.resize(src, (width, height), interpolation=cv2.INTER_AREA)

    def cvt_gray(self, src: Any) -> Any:
        import cv2

        if getattr(src, "ndim", 2) == 3:
            return cv2.cvtColor(src, cv2.COLOR_BGR2GRAY)
        return src

    def gaussian_blur(self, src: Any, ksize: int, sigma: float) -> Any:
        import cv2

        return cv2.GaussianBlur(src, (ksize, ksize), sigma)

    def bg_subtract(self, src: Any) -> Any:
        return self._mog.apply(src)

    def threshold(self, src: Any, thresh: int, maxval: int) -> Any:
        import cv2

        return cv2.threshold(src, thresh, maxval, cv2.THRESH_BINARY)[1]

    def morphology(self, src: Any, op: str, ksize: int) -> Any:
        import cv2

        flag = cv2.MORPH_OPEN if op == "open" else cv2.MORPH_CLOSE
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ksize, ksize))
        return cv2.morphologyEx(src, flag, kernel)

    def warp_affine(self, src: Any, matrix: Any, width: int, height: int) -> Any:
        import cv2

        return cv2.warpAffine(
            src, matrix, (width, height),
            flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE,
        )

    def sobel(self, src: Any, dx: int, dy: int, ksize: int) -> Any:
        import cv2

        return cv2.Sobel(src, cv2.CV_32F, dx, dy, ksize=ksize)

    def find_contours(self, src: Any) -> list[Any]:
        import cv2

        return list(cv2.findContours(src, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0])

    def reset_state(self) -> None:
        import cv2

        self._mog = cv2.createBackgroundSubtractorMOG2(
            history=200, varThreshold=24, detectShadows=False
        )


class CoolBackend(BaselineBackend):
    name: BackendName = "cool"  # type: ignore[assignment]
    accelerated_ops: tuple[str, ...] = ()

    def __init__(self) -> None:
        super().__init__()
        cool = _probe_cool_module()
        self.accelerated_ops = ()
        if cool is None:
            return
        found: list[str] = []
        # Map COOL module function names to baseline method names.
        mapping = {
            "resize": "resize", "cvtColor": "cvt_gray",
            "GaussianBlur": "gaussian_blur", "threshold": "threshold",
            "morphologyEx": "morphology", "warpAffine": "warp_affine",
            "Sobel": "sobel", "findContours": "find_contours",
            "createBackgroundSubtractorMOG2": "bg_subtract",
        }
        op_name_by_cool = {
            "resize": "resize", "cvtColor": "cvt_gray",
            "GaussianBlur": "gaussian_blur", "threshold": "threshold",
            "morphologyEx": "morphology", "warpAffine": "warp_affine",
            "Sobel": "sobel", "findContours": "find_contours",
            "createBackgroundSubtractorMOG2": "bg_subtract",
        }
        import cv2

        for cool_name in ("resize", "cvtColor", "GaussianBlur", "threshold",
                          "morphologyEx", "warpAffine", "Sobel", "findContours",
                          "createBackgroundSubtractorMOG2"):
            if hasattr(cool, cool_name):
                found.append(op_name_by_cool[cool_name])
                _bind_cool_override(self, cool, cool_name, mapping[cool_name])
        # Re-install MOG if COOL provides its own subtractor.
        if hasattr(cool, "createBackgroundSubtractorMOG2"):
            try:
                self._mog = cool.createBackgroundSubtractorMOG2()
            except Exception:
                pass
        self.accelerated_ops = tuple(found)


def _bind_cool_override(self: CoolBackend, cool: Any, cool_name: str, method: str) -> None:
    import cv2

    fn = getattr(cool, cool_name)
    if method == "resize":
        def resize(src: Any, width: int, height: int) -> Any:
            try:
                return fn(src, (width, height), interpolation=cv2.INTER_AREA)
            except TypeError:
                return fn(src, width, height)
        self.resize = resize  # type: ignore[method-assign]
    elif method == "cvt_gray":
        def cvt_gray(src: Any) -> Any:
            if getattr(src, "ndim", 2) == 3:
                return fn(src, cv2.COLOR_BGR2GRAY)
            return src
        self.cvt_gray = cvt_gray  # type: ignore[method-assign]
    elif method == "gaussian_blur":
        def gaussian_blur(src: Any, ksize: int, sigma: float) -> Any:
            return fn(src, (ksize, ksize), sigma)
        self.gaussian_blur = gaussian_blur  # type: ignore[method-assign]
    elif method == "threshold":
        def threshold(src: Any, thresh: int, maxval: int) -> Any:
            r = fn(src, thresh, maxval, cv2.THRESH_BINARY)
            return r[1] if isinstance(r, tuple) else r
        self.threshold = threshold  # type: ignore[method-assign]
    elif method == "morphology":
        def morphology(src: Any, op: str, ksize: int) -> Any:
            flag = cv2.MORPH_OPEN if op == "open" else cv2.MORPH_CLOSE
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ksize, ksize))
            return fn(src, flag, kernel)
        self.morphology = morphology  # type: ignore[method-assign]
    elif method == "warp_affine":
        def warp_affine(src: Any, matrix: Any, width: int, height: int) -> Any:
            return fn(src, matrix, (width, height),
                      flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        self.warp_affine = warp_affine  # type: ignore[method-assign]
    elif method == "sobel":
        def sobel(src: Any, dx: int, dy: int, ksize: int) -> Any:
            return fn(src, cv2.CV_32F, dx, dy, ksize=ksize)
        self.sobel = sobel  # type: ignore[method-assign]
    elif method == "find_contours":
        def find_contours(src: Any) -> list[Any]:
            r = fn(src, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            seq = r[0] if isinstance(r, tuple) else r
            return list(seq)
        self.find_contours = find_contours  # type: ignore[method-assign]


def get_backend(name: BackendName) -> VisionBackend:
    """Return the requested backend. "cool" falls back to baseline (with one warning) when
    cool_available() is False. Never raises."""
    global _WARNED_ONCE
    if name == "baseline":
        return BaselineBackend()
    if cool_available():
        try:
            return CoolBackend()
        except Exception:
            pass
    if not _WARNED_ONCE:
        _WARNED_ONCE = True
        logger.warning(
            "vision: COOL build not found (probed cv2.cool, cool, opencv_cool); using baseline backend"
        )
    b = BaselineBackend()
    return b


def backend_info(backend: VisionBackend) -> BackendInfo:
    """Report {name, opencv_version, cool_version, arch, cool_available} for `backend`."""
    import cv2

    nm: BackendName = getattr(backend, "name", "baseline")
    return {
        "name": nm,
        "opencv_version": cv2.__version__,
        "cool_version": cool_version() if nm == "cool" else None,
        "arch": platform.machine(),
        "cool_available": cool_available(),
    }
