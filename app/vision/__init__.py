"""Public surface of the vision module. Consumers import from here."""
from app.vision.backend import (
    VisionBackend,
    backend_info,
    cool_available,
    cool_version,
    get_backend,
)
from app.vision.ops import OP_NAMES, timed
from app.vision.pipeline import (
    HISTORY_LEN,
    WORK_HEIGHT,
    WORK_WIDTH,
    PipelineState,
    analyze_frame,
    create_pipeline_state,
    detect_roi,
)
from app.vision.source import SourceError, iter_frames, probe_source

__all__ = [
    "VisionBackend", "backend_info", "cool_available", "cool_version", "get_backend",
    "OP_NAMES", "timed",
    "PipelineState", "analyze_frame", "create_pipeline_state", "detect_roi",
    "WORK_WIDTH", "WORK_HEIGHT", "HISTORY_LEN",
    "SourceError", "iter_frames", "probe_source",
]
