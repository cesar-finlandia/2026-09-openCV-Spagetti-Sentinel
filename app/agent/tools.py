"""MCP-style tool registry — REQ-F07."""
from __future__ import annotations

import time
from typing import Any, Callable, TypedDict


class ToolSpec(TypedDict):
    name: str
    description: str
    input_schema: dict[str, Any]
    output_key: str
    fn: Callable[..., dict[str, Any]]


class ToolError(Exception):
    """Raised only by call_tool() for an unknown tool name or a schema-invalid argument set."""


_CONTEXT: dict[str, Any] = {}


def set_tool_context(ctx: dict) -> None:
    _CONTEXT.clear()
    _CONTEXT.update(ctx)


def clear_tool_context() -> None:
    _CONTEXT.clear()


def _check_args(schema: dict[str, Any], args: dict[str, Any]) -> str | None:
    try:
        from src.resilience import validate

        res = validate(schema, args)
        errs = res.get("errors", []) if isinstance(res, dict) else list(res or [])
        if errs:
            first = errs[0]
            if isinstance(first, dict):
                return f"{first.get('path', '/')}: {first.get('message', '')}"
            return str(first)
        return None
    except Exception:
        # Minimal fallback validation.
        try:
            req = schema.get("required", [])
            props = schema.get("properties", {})
            for r in req:
                if r not in args:
                    return f"/{r}: required"
            for k, v in args.items():
                if k not in props:
                    if schema.get("additionalProperties") is False:
                        return f"/{k}: unexpected"
                    continue
                spec = props[k]
                if spec.get("type") == "integer" and not isinstance(v, int):
                    return f"/{k}: expected integer"
                if spec.get("type") == "string" and not isinstance(v, str):
                    return f"/{k}: expected string"
                if isinstance(v, int) and "minimum" in spec and v < spec["minimum"]:
                    return f"/{k}: below minimum"
                if isinstance(v, str) and "minLength" in spec and len(v) < spec["minLength"]:
                    return f"/{k}: too short"
            return None
        except Exception as err:
            return str(err)


def _tool_probe_source(source: str) -> dict[str, Any]:
    from app.vision import probe_source

    return {"info": probe_source(source)}


def _tool_detect_roi(frame_index: int) -> dict[str, Any]:
    from app.vision import detect_roi
    from app.vision import pipeline as _pipeline

    backend = _CONTEXT.get("backend")
    frame = _CONTEXT.get("frame")
    if backend is None or frame is None:
        return {"error": "no frame context"}
    import numpy as np

    gray = _pipeline.timed  # keep ref (no-op)
    # Convert current frame to gray via backend.
    small = backend.resize(frame, _pipeline.WORK_WIDTH, _pipeline.WORK_HEIGHT)
    gray_img = backend.cvt_gray(small)
    roi = detect_roi(backend, gray_img)
    return {"roi": roi, "frame_index": frame_index}


def _tool_score_frame(frame_index: int, t_ms: int) -> dict[str, Any]:
    from app.vision import pipeline as _pipeline

    backend = _CONTEXT.get("backend")
    state = _CONTEXT.get("state")
    cfg = _CONTEXT.get("cfg")
    frame = _CONTEXT.get("frame")
    scores = _pipeline.analyze_frame(frame, state, cfg, backend, frame_index, t_ms)
    return {"scores": scores}


def _tool_capture_evidence(frame_index: int, note: str = "") -> dict[str, Any]:
    ctx = _CONTEXT
    store = ctx.get("store")
    cfg = ctx.get("cfg", {})
    ring = ctx.get("ring")
    history = ctx.get("history", [])
    frames = list(ring) if ring is not None else []
    run_id = cfg.get("run_id", "run")
    clip = store.put_clip(run_id, frames, {"frame_index": frame_index})
    if frames:
        still = store.put_frame(run_id, frames[-1], {"frame_index": frame_index})
    else:
        still = {"uri": "", "bytes": 0, "backend": "local", "degraded": True}
    scores_json = store.put_json(run_id, "scores", {"history": list(history)[-30:]})
    return {"evidence_uri": clip.get("uri") or still.get("uri"),
            "clip": clip.get("uri"), "frame": still.get("uri"),
            "scores_json": scores_json.get("uri"), "bytes": clip.get("bytes", 0),
            "backend": clip.get("backend", "local"),
            "degraded": bool(clip.get("degraded")), "note": note}


TOOLS: dict[str, ToolSpec] = {
    "probe_source": {
        "name": "probe_source",
        "description": "Open a video source and report whether it can be read, its frame count, fps and resolution.",
        "input_schema": {
            "type": "object", "additionalProperties": False, "required": ["source"],
            "properties": {"source": {"type": "string", "minLength": 1}},
        },
        "output_key": "info",
        "fn": _tool_probe_source,
    },
    "detect_roi": {
        "name": "detect_roi",
        "description": "Locate the print-bed region of interest in one frame using OpenCV 5 gradient energy.",
        "input_schema": {
            "type": "object", "additionalProperties": False, "required": ["frame_index"],
            "properties": {"frame_index": {"type": "integer", "minimum": 0}},
        },
        "output_key": "roi",
        "fn": _tool_detect_roi,
    },
    "score_frame": {
        "name": "score_frame",
        "description": "Run the OpenCV 5 analysis pipeline over one frame and return the measured VisionScores JSON.",
        "input_schema": {
            "type": "object", "additionalProperties": False, "required": ["frame_index", "t_ms"],
            "properties": {
                "frame_index": {"type": "integer", "minimum": 0},
                "t_ms": {"type": "integer", "minimum": 0},
            },
        },
        "output_key": "scores",
        "fn": _tool_score_frame,
    },
    "capture_evidence": {
        "name": "capture_evidence",
        "description": "Persist the frames around a given index as a clip plus a still frame and the measurement JSON.",
        "input_schema": {
            "type": "object", "additionalProperties": False, "required": ["frame_index"],
            "properties": {
                "frame_index": {"type": "integer", "minimum": 0},
                "note": {"type": "string"},
            },
        },
        "output_key": "evidence_uri",
        "fn": _tool_capture_evidence,
    },
}


def call_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Validate `args` against the tool's input_schema, invoke it, return its dict result."""
    spec = TOOLS.get(name)
    if spec is None:
        raise ToolError(f"unknown tool: {name}")
    err = _check_args(spec["input_schema"], args or {})
    if err:
        raise ToolError(f"invalid args for {name}: {err}")
    t0 = time.perf_counter()
    try:
        result = spec["fn"](**(args or {}))
    except Exception as err2:
        result = {"error": f"{type(err2).__name__}: {err2}"}
    if not isinstance(result, dict):
        result = {spec["output_key"]: result}
    result["_tool"] = name
    result["_ms"] = round((time.perf_counter() - t0) * 1000.0, 3)
    return result


def tool_manifest() -> list[dict[str, Any]]:
    """The registry as JSON: [{name, description, input_schema, output_key}]."""
    return [{"name": t["name"], "description": t["description"],
             "input_schema": t["input_schema"], "output_key": t["output_key"]}
            for t in TOOLS.values()]
