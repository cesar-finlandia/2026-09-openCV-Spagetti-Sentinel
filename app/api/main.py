"""FastAPI application. Mounted at "/" behind uvicorn."""
from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger("api.main")

APP_STARTED_AT = time.time()

app = FastAPI(title="Spaghetti Sentinel")


@app.on_event("startup")
async def _startup() -> None:
    try:
        import cv2

        major = int(str(cv2.__version__).split(".")[0])
        if major != 5:
            logger.error("FATAL: OpenCV major version %s; this project requires OpenCV 5 (MT-1)", major)
            app.state.opencv_ok = False
        else:
            app.state.opencv_ok = True
    except Exception as err:
        logger.error("FATAL: OpenCV import failed (%s)", type(err).__name__)
        app.state.opencv_ok = False
    try:
        from app.config.settings import load_settings
        from app.vision import backend_info, get_backend

        logger.info("backend_info: %s",
                    backend_info(get_backend(load_settings().backend)))
    except Exception as err:
        logger.warning("startup: backend probe failed (%s)", type(err).__name__)


# Chassis SSE router provides GET /events/stream. Do not reimplement it.
try:
    from src.platform.transport.stream_router import router as events_router

    app.include_router(events_router)
except Exception as err:
    logger.warning("startup: events router unavailable (%s)", type(err).__name__)


@app.get("/healthz")
def healthz() -> JSONResponse:
    try:
        from app.api.version import BUILD_MARKER, build_info

        info = build_info()
        # Cache evidence health on app state after first call.
        ev = getattr(app.state, "evidence_health", None)
        if ev is None:
            try:
                from app.evidence import create_evidence_store

                ev = create_evidence_store().health()
            except Exception:
                ev = {"backend": "local", "bucket": None, "writable": False}
            app.state.evidence_health = ev
        status = "ok"
        try:
            if getattr(app.state, "opencv_ok", True) is False:
                status = "degraded"
        except Exception:
            pass
        body = {"status": status, **info,
                "evidence": {"backend": ev.get("backend"),
                             "bucket": ev.get("bucket"),
                             "writable": ev.get("writable")},
                "uptime_s": round(time.time() - APP_STARTED_AT, 1)}
        # Never leak secrets.
        return JSONResponse(body)
    except Exception:
        try:
            from app.api.version import BUILD_MARKER
        except Exception:
            BUILD_MARKER = "dev"
        return JSONResponse({"status": "degraded", "build_marker": BUILD_MARKER})


@app.get("/api/fixtures")
def api_fixtures() -> JSONResponse:
    try:
        with open("fixtures/manifest.json", encoding="utf-8") as fh:
            return JSONResponse(json.load(fh))
    except Exception:
        return JSONResponse({"synthetic": True, "clips": []})


@app.get("/api/tools")
def api_tools() -> JSONResponse:
    from app.agent import tool_manifest

    return JSONResponse(tool_manifest())


def _resolve_source(body: dict) -> tuple[str | None, str | None]:
    """Returns (source, error)."""
    fixture_id = body.get("fixture_id")
    source = body.get("source")
    if fixture_id:
        try:
            manifest = json.load(open("fixtures/manifest.json", encoding="utf-8"))
            for c in manifest.get("clips", []):
                if c["id"] == fixture_id:
                    return c["path"], None
            return None, f"unknown fixture_id: {fixture_id}"
        except Exception:
            return None, "fixtures manifest unavailable"
    if source:
        return str(source), None
    try:
        manifest = json.load(open("fixtures/manifest.json", encoding="utf-8"))
        clips = manifest.get("clips", [])
        if clips:
            return clips[0]["path"], None
    except Exception:
        pass
    return None, "no source and no fixtures"


@app.post("/api/runs")
async def api_runs(request: Request) -> JSONResponse:
    from app.api.runs import REGISTRY
    from app.vision.source import SourceError

    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}
    source, error = _resolve_source(body)
    if source is None:
        return JSONResponse({"detail": error or "no source"}, status_code=400)
    try:
        from app.vision import probe_source

        probe_source(source)
    except SourceError as err:
        return JSONResponse({"detail": str(err)}, status_code=400)
    except Exception as err:
        return JSONResponse({"detail": f"cannot open source: {type(err).__name__}"},
                            status_code=400)
    if REGISTRY.active() is not None:
        act = REGISTRY.active()
        return JSONResponse({"detail": "a run is already active",
                             "run_id": act.run_id if act else None}, status_code=409)
    cfg = REGISTRY.build_config(source, body.get("backend"), body.get("replay"),
                                body.get("sample_every_n"), body.get("max_frames"))
    record = await REGISTRY.start(cfg)
    return JSONResponse({"run_id": cfg["run_id"], "trace_id": cfg["run_id"],
                         "stream": f"/events/stream?trace_id={cfg['run_id']}"})


@app.post("/api/runs/upload")
async def api_runs_upload(request: Request, file: UploadFile) -> JSONResponse:
    from app.api.runs import MAX_UPLOAD_BYTES, REGISTRY
    from app.config.settings import load_settings

    ctype = (file.content_type or "")
    if not ctype.startswith("video/"):
        return JSONResponse({"detail": f"unsupported content type: {ctype}"}, status_code=415)
    try:
        settings = load_settings()
        updir = os.path.join(settings.evidence_dir, "uploads")
        os.makedirs(updir, exist_ok=True)
    except Exception:
        updir = tempfile.gettempdir()
    ext = ".mp4"
    try:
        orig = (file.filename or "").lower()
        for e in (".mp4", ".mov", ".mkv", ".avi"):
            if orig.endswith(e):
                ext = e
                break
    except Exception:
        pass
    dest = os.path.join(updir, uuid4().hex + ext)
    try:
        size = 0
        with open(dest, "wb") as fh:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    try:
                        fh.close()
                        os.unlink(dest)
                    except Exception:
                        pass
                    return JSONResponse({"detail": "upload exceeds 200 MB"}, status_code=413)
                fh.write(chunk)
    except Exception as err:
        return JSONResponse({"detail": f"upload failed: {type(err).__name__}"}, status_code=400)
    if REGISTRY.active() is not None:
        act = REGISTRY.active()
        return JSONResponse({"detail": "a run is already active",
                             "run_id": act.run_id if act else None}, status_code=409)
    cfg = REGISTRY.build_config(dest, None, False, None, None)
    record = await REGISTRY.start(cfg)
    return JSONResponse({"run_id": cfg["run_id"], "trace_id": cfg["run_id"],
                         "stream": f"/events/stream?trace_id={cfg['run_id']}"})


@app.get("/api/runs/{run_id}")
def api_run_get(run_id: str) -> JSONResponse:
    from app.api.runs import REGISTRY

    rec = REGISTRY.get(run_id)
    if rec is None:
        return JSONResponse({"detail": "unknown run"}, status_code=404)
    return JSONResponse({"run_id": rec.run_id, "status": rec.status, "summary": rec.summary})


@app.post("/api/runs/{run_id}/approve")
async def api_run_approve(run_id: str, request: Request) -> JSONResponse:
    from app.api.runs import REGISTRY

    rec = REGISTRY.get(run_id)
    if rec is None:
        return JSONResponse({"detail": "unknown run"}, status_code=404)
    try:
        body = await request.json()
    except Exception:
        body = {}
    approval_id = (body or {}).get("approval_id", "")
    approved = bool((body or {}).get("approved", False))
    if REGISTRY.resolve_approval(approval_id, approved):
        return JSONResponse({"resolved": True})
    return JSONResponse({"detail": "no approval pending"}, status_code=409)


@app.get("/events")
def api_events(trace_id: str | None = None) -> JSONResponse:
    from app.api.publisher import get_publisher

    pub = get_publisher(trace_id)
    if pub is None:
        return JSONResponse({"status": "complete", "trace_id": trace_id,
                             "events": [], "degraded": False})
    # "status": "complete" is the chassis FallbackSnapshot shape (TRN-RES-03):
    # the browser's parseSnapshot requires it before accepting the snapshot.
    return JSONResponse({"status": "complete", **pub.collect()})


@app.get("/api/evidence/{key:path}")
def api_evidence(key: str) -> Any:
    from app.config.settings import load_settings
    from app.evidence import create_evidence_store

    if ".." in key.replace("\\", "/").split("/"):
        return JSONResponse({"detail": "invalid key"}, status_code=400)
    try:
        store = create_evidence_store()
    except Exception:
        return JSONResponse({"detail": "store unavailable"}, status_code=404)
    if getattr(store, "backend", "local") == "s3":
        return JSONResponse({"detail": "use the presigned URL"}, status_code=501)
    try:
        settings = load_settings()
        path = os.path.join(settings.evidence_dir, key.replace("/", os.sep))
    except Exception:
        return JSONResponse({"detail": "missing"}, status_code=404)
    if not os.path.isfile(path):
        return JSONResponse({"detail": "missing"}, status_code=404)
    ctype = "application/octet-stream"
    if path.endswith(".mp4"):
        ctype = "video/mp4"
    elif path.endswith(".png"):
        ctype = "image/png"
    elif path.endswith(".json"):
        ctype = "application/json"
    return FileResponse(path, media_type=ctype)


# Static SPA mount LAST so it cannot shadow /api/* or /events*.
try:
    if os.path.isfile(os.path.join("web", "dist", "index.html")):
        if os.path.isdir(os.path.join("web", "dist", "assets")):
            app.mount("/assets", StaticFiles(directory=os.path.join("web", "dist", "assets")),
                      name="assets")

        @app.get("/{path:path}")
        def spa_fallback(path: str) -> Any:
            if path.startswith("api/") or path.startswith("events") or path == "healthz":
                return JSONResponse({"detail": "not found"}, status_code=404)
            return FileResponse(os.path.join("web", "dist", "index.html"))
    else:
        @app.get("/{path:path}")
        def spa_missing(path: str) -> Any:
            if path.startswith("api/") or path.startswith("events") or path == "healthz":
                return JSONResponse({"detail": "not found"}, status_code=404)
            return JSONResponse(
                {"detail": "UI bundle not built — run `pnpm --dir web build`"}, status_code=404)
except Exception:
    pass
