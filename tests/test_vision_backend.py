"""DP-VISION backend tests."""
from __future__ import annotations


def test_baseline_name():
    from app.vision.backend import get_backend

    assert get_backend("baseline").name == "baseline"


def test_cool_never_raises():
    from app.vision.backend import get_backend

    b = get_backend("cool")
    assert b.name in ("cool", "baseline")


def test_opencv_major_5_through_backend():
    from app.vision.backend import backend_info, get_backend

    info = backend_info(get_backend("baseline"))
    assert info["opencv_version"].split(".")[0] == "5"


def test_backends_expose_ops():
    from app.vision.backend import get_backend
    from app.vision.ops import OP_NAMES

    for name in ("baseline", "cool"):
        b = get_backend(name)
        for op in OP_NAMES:
            if op == "find_contours":
                continue
            method = {
                "resize": "resize", "cvt_gray": "cvt_gray",
                "gaussian_blur": "gaussian_blur", "bg_subtract": "bg_subtract",
                "threshold": "threshold", "morphology": "morphology",
                "warp_affine": "warp_affine", "sobel": "sobel",
            }[op]
            assert callable(getattr(b, method, None)), (name, op)
