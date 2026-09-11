"""The fixed vocabulary of accelerated operations (OP_NAMES) and their timing helper.

OP_NAMES is the closed set of operations the COOL track claims as "the core workload".
Every backend implements exactly these, and VisionScores.ops_ms is keyed by exactly these.
"""
from __future__ import annotations

import time
from typing import Callable, TypeVar

OP_NAMES: tuple[str, ...] = (
    "resize",
    "cvt_gray",
    "gaussian_blur",
    "bg_subtract",
    "threshold",
    "morphology",
    "warp_affine",
    "sobel",
    "find_contours",
)

T = TypeVar("T")


def timed(op_name: str, sink: dict[str, float], fn: Callable[[], T]) -> T:
    """Run `fn`, add its wall-clock milliseconds to sink[op_name], return its value.

    Accumulates (+=) rather than overwrites, so an op called twice per frame reports its
    total. Uses time.perf_counter(). Never swallows an exception from `fn`.
    """
    t0 = time.perf_counter()
    try:
        return fn()
    finally:
        dt = (time.perf_counter() - t0) * 1000.0
        sink[op_name] = sink.get(op_name, 0.0) + dt
