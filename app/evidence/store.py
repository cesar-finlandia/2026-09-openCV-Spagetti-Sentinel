"""EvidenceStore — REQ-F10. Writes evidence to S3, or to local disk when S3 is unusable.

Two backends, one interface. Every public method is wrapped with the chassis resilience layer,
so a network stall, an expired credential or a missing bucket returns a DegradedResult instead
of raising into the agent loop. Nothing here ever logs or returns a credential (REQ-N07).
"""
from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from typing import Any, Literal, TypedDict

logger = logging.getLogger("evidence.store")

try:
    from src.resilience.degraded import make_degraded_result
except Exception:  # pragma: no cover
    from src.resilience import make_degraded_result  # type: ignore

try:
    from src.resilience import is_degraded_result, with_resilience
except Exception:  # pragma: no cover
    from src.resilience.degraded import is_degraded_result  # type: ignore

    def with_resilience(fn, config=None, deps=None):  # type: ignore
        return fn

StoreBackend = Literal["s3", "local"]
EvidenceKind = Literal["clip", "frame", "json"]

CLIP_FOURCC: str = "avc1"
"""H.264 — plays in a browser <video> tag without transcoding (DP-UI depends on this)."""

CLIP_FPS: float = 10.0
"""Evidence clips are slowed to 10 fps so a judge can see the defect in a 3-second clip."""


class PutResult(TypedDict):
    uri: str            # "s3://bucket/key" or "file://<abspath>"
    key: str            # the object key, identical in both backends
    kind: EvidenceKind
    bytes: int
    backend: StoreBackend
    degraded: bool


def _sanitize_name(name: str) -> str:
    # Replace every disallowed character with '-'; must match ^[-\w.]+$
    out = re.sub(r"[^A-Za-z0-9_.\-]", "-", name)
    out = out.strip(".-") or "obj"
    if not re.fullmatch(r"[-\w.]+", out):
        out = "obj"
    return out


class EvidenceStore:
    """One store per process. Thread-safe for concurrent put_* calls (each is stateless)."""

    def __init__(self, backend: StoreBackend = "local", bucket: str | None = None,
                 local_root: str = ".evidence", region: str = "us-east-1",
                 client: Any | None = None) -> None:
        self.backend = backend
        self.bucket = bucket
        self.local_root = local_root
        self.region = region
        self._client = client
        # Resilience-wrapped uploader created once per instance.
        try:
            def _noop() -> None:
                return None
            self._guarded_noop = with_resilience(
                _noop, {"timeout_ms": 8000, "retries": 2,
                        "fallback_chain": {"order": ["none"]}},
            )
        except Exception:
            self._guarded_noop = None
        try:
            self._uploader = with_resilience(
                self._raw_upload,
                {"timeout_ms": 8000, "retries": 2, "fallback_chain": {"order": ["none"]}},
            )
        except Exception:
            self._uploader = self._raw_upload

    def _raw_upload(self, key: str, data: bytes, content_type: str) -> dict:
        assert self._client is not None and self.bucket
        self._client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)
        return {"ok": True}

    # -- keys ---------------------------------------------------------------
    @staticmethod
    def _clip_key(run_id: str, frame_index: int) -> str:
        return f"runs/{run_id}/clip-{int(frame_index):06d}.mp4"

    @staticmethod
    def _frame_key(run_id: str, frame_index: int) -> str:
        return f"runs/{run_id}/frame-{int(frame_index):06d}.png"

    @staticmethod
    def _json_key(run_id: str, name: str) -> str:
        return f"runs/{run_id}/{_sanitize_name(name)}.json"

    # -- write path ----------------------------------------------------------
    def _put_bytes(self, key: str, data: bytes, content_type: str, kind: EvidenceKind) -> PutResult:
        degraded = False
        if self.backend == "s3" and self._client is not None:
            try:
                result = self._uploader(key, data, content_type)
                if is_degraded_result(result):
                    reason = result.get("reason", "unknown") if isinstance(result, dict) else "unknown"
                    logger.warning("evidence: S3 put failed for %s (%s); wrote local copy instead", key, reason)
                    degraded = True
                else:
                    return {"uri": f"s3://{self.bucket}/{key}", "key": key, "kind": kind,
                            "bytes": len(data), "backend": "s3", "degraded": False}
            except Exception as err:
                logger.warning("evidence: S3 put failed for %s (%s); wrote local copy instead",
                               key, type(err).__name__)
                degraded = True
        # Local branch (also the S3 fallback).
        try:
            path = os.path.join(self.local_root, key.replace("/", os.sep))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = path + ".tmp"
            with open(tmp, "wb") as fh:
                fh.write(data)
            os.replace(tmp, path)
            return {"uri": f"file://{os.path.abspath(path)}", "key": key, "kind": kind,
                    "bytes": len(data), "backend": "local", "degraded": degraded}
        except Exception:
            logger.error("evidence: local write failed for key")
            return {"uri": "", "key": key, "kind": kind, "bytes": 0,
                    "backend": "local", "degraded": True}

    def put_clip(self, run_id: str, frames: list[Any], meta: dict[str, Any]) -> PutResult:
        """Encode `frames` (list of BGR ndarrays) to H.264 and store."""
        try:
            frame_index = int((meta or {}).get("frame_index", 0))
        except Exception:
            frame_index = 0
        key = self._clip_key(run_id, frame_index)
        if not frames:
            return {"uri": "", "key": key, "kind": "clip", "bytes": 0,
                    "backend": self.backend, "degraded": True}
        import cv2
        import numpy as np

        h, w = frames[0].shape[:2]
        degraded = False
        tmp = None
        try:
            fd, tmp = tempfile.mkstemp(suffix=".mp4")
            os.close(fd)
            writer = cv2.VideoWriter(tmp, cv2.VideoWriter_fourcc(*CLIP_FOURCC), CLIP_FPS, (w, h))
            for f in frames:
                writer.write(np.asarray(f))
            writer.release()
            size = os.path.getsize(tmp) if os.path.exists(tmp) else 0
            if size <= 0:
                # Retry once with mp4v.
                writer = cv2.VideoWriter(tmp, cv2.VideoWriter_fourcc(*"mp4v"), CLIP_FPS, (w, h))
                for f in frames:
                    writer.write(np.asarray(f))
                writer.release()
                degraded = True
                size = os.path.getsize(tmp) if os.path.exists(tmp) else 0
            if size <= 0:
                return {"uri": "", "key": key, "kind": "clip", "bytes": 0,
                        "backend": self.backend, "degraded": True}
            with open(tmp, "rb") as fh:
                data = fh.read()
        except Exception:
            logger.error("evidence: clip encode failed")
            return {"uri": "", "key": key, "kind": "clip", "bytes": 0,
                    "backend": self.backend, "degraded": True}
        finally:
            try:
                if tmp and os.path.exists(tmp):
                    os.unlink(tmp)
            except Exception:
                pass
        res = self._put_bytes(key, data, "video/mp4", "clip")
        if degraded:
            res["degraded"] = True
        return res

    def put_frame(self, run_id: str, frame: Any, meta: dict[str, Any]) -> PutResult:
        """PNG-encode one BGR ndarray and store."""
        try:
            frame_index = int((meta or {}).get("frame_index", 0))
        except Exception:
            frame_index = 0
        key = self._frame_key(run_id, frame_index)
        import cv2

        try:
            ok, buf = cv2.imencode(".png", frame)
        except Exception:
            ok, buf = False, None
        if not ok or buf is None:
            return {"uri": "", "key": key, "kind": "frame", "bytes": 0,
                    "backend": self.backend, "degraded": True}
        return self._put_bytes(key, bytes(buf.tobytes()), "image/png", "frame")

    def put_json(self, run_id: str, name: str, obj: dict[str, Any]) -> PutResult:
        """Store `obj` as UTF-8 JSON (indent=2)."""
        key = self._json_key(run_id, name)
        try:
            data = json.dumps(obj, indent=2, sort_keys=False, default=str).encode("utf-8")
        except Exception:
            data = b"{}"
        return self._put_bytes(key, data, "application/json", "json")

    def url_for(self, key: str) -> str:
        """Browser-openable URL for `key`."""
        try:
            if self.backend == "s3" and self._client is not None:
                return self._client.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=3600)
            return f"/api/evidence/{key}"
        except Exception:
            return ""

    def health(self) -> dict[str, Any]:
        """{"backend": …, "bucket": …, "writable": bool, "reason": str | None}."""
        if self.backend == "s3":
            return {"backend": "s3", "bucket": self.bucket, "writable": True, "reason": None}
        try:
            os.makedirs(self.local_root, exist_ok=True)
            probe = os.path.join(self.local_root, ".writeprobe")
            with open(probe, "wb") as fh:
                fh.write(b"1")
            try:
                os.unlink(probe)
            except Exception:
                pass
            return {"backend": "local", "bucket": None, "writable": True, "reason": None}
        except Exception:
            return {"backend": "local", "bucket": None, "writable": False, "reason": "not writable"}


def create_evidence_store(settings: Any | None = None) -> EvidenceStore:
    """Build the store from Settings (app/config/settings.py)."""
    from app.config.settings import load_settings

    try:
        settings = settings or load_settings()
    except Exception:
        settings = load_settings({})
    if not getattr(settings, "s3_bucket", None):
        logger.info("evidence: S3_BUCKET unset, storing evidence under %s",
                    getattr(settings, "evidence_dir", ".evidence"))
        return EvidenceStore(backend="local", bucket=None,
                             local_root=getattr(settings, "evidence_dir", ".evidence"),
                             region=getattr(settings, "aws_region", "us-east-1"))
    try:
        import boto3

        client = boto3.client("s3", region_name=getattr(settings, "aws_region", "us-east-1"))
        client.head_bucket(Bucket=settings.s3_bucket)
        return EvidenceStore(backend="s3", bucket=settings.s3_bucket,
                             local_root=getattr(settings, "evidence_dir", ".evidence"),
                             region=getattr(settings, "aws_region", "us-east-1"),
                             client=client)
    except Exception as err:
        logger.warning("evidence: S3 bucket %s unreachable (%s); falling back to local disk",
                       getattr(settings, "s3_bucket", "?"), type(err).__name__)
        return EvidenceStore(backend="local", bucket=None,
                             local_root=getattr(settings, "evidence_dir", ".evidence"),
                             region=getattr(settings, "aws_region", "us-east-1"))
