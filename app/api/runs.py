"""RunRegistry — run lifecycle, approval futures, and the single-active-run rule."""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.contracts.types import AgentDecision, RunConfig, RunSummary

logger = logging.getLogger("api.runs")

MAX_UPLOAD_BYTES: int = 200 * 1024 * 1024
"""200 MB upload ceiling."""


class RunRecord:
    run_id: str
    cfg: RunConfig
    status: str            # "running" | "done" | "error"
    summary: RunSummary | None
    started_at: str
    pending_approval: AgentDecision | None

    def __init__(self, run_id: str, cfg: RunConfig) -> None:
        self.run_id = run_id
        self.cfg = cfg
        self.status = "running"
        self.summary = None
        self.started_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        self.pending_approval = None


class RunRegistry:
    """One active run per process. Additional starts get HTTP 409."""

    def __init__(self) -> None:
        self._active: RunRecord | None = None
        self._task: asyncio.Task | None = None
        self._pending: tuple[str, asyncio.Future] | None = None
        self._records: dict[str, RunRecord] = {}

    def active(self) -> RunRecord | None:
        if self._active is not None and self._active.status == "running":
            return self._active
        return None

    def get(self, run_id: str) -> RunRecord | None:
        return self._records.get(run_id)

    def build_config(self, source: str, backend: str | None, replay: bool | None,
                     sample_every_n: int | None, max_frames: int | None) -> RunConfig:
        from app.config.settings import load_settings

        settings = load_settings()
        be = (backend or settings.backend).strip().lower()
        if be not in ("cool", "baseline"):
            be = settings.backend
        try:
            sen = int(sample_every_n) if sample_every_n is not None else settings.sample_every_n
        except Exception:
            sen = settings.sample_every_n
        try:
            mf = int(max_frames) if max_frames is not None else settings.max_frames
        except Exception:
            mf = settings.max_frames
        sen = max(1, min(30, sen))
        mf = max(1, min(5000, mf))
        # Full hyphenated UUID (not hex[:12]): the chassis EventEnvelope schema
        # declares trace_id as format uuid, and the browser validates with ajv
        # (which enforces formats, unlike Python jsonschema's default). Since
        # trace_id == run_id (blueprint §2.1), the run id itself must be a uuid.
        run_id = str(uuid4())
        try:
            fx = settings.fixtures_dir
        except Exception:
            fx = "fixtures"
        synthetic = source.replace("\\", "/").startswith(fx.replace("\\", "/"))
        return {
            "run_id": run_id, "source": source, "backend": be,
            "sample_every_n": sen, "max_frames": mf, "roi": None,
            "thresholds": dict(settings.thresholds),
            "synthetic": synthetic,
            "replay": bool(replay) if replay is not None else settings.replay,
            "evidence_prefix": run_id,
        }

    async def start(self, cfg: RunConfig) -> RunRecord:
        from app.agent import run_agent

        from app.api.publisher import create_publisher

        record = RunRecord(cfg["run_id"], cfg)
        pub = create_publisher(cfg["run_id"])

        async def _run() -> None:
            try:
                summary = await run_agent(cfg, pub.publish, self.approver)
                record.summary = summary
                record.status = "error" if summary.get("degraded") else "done"
            finally:
                record.pending_approval = None
                if self._active is record:
                    self._active = None
                await pub.close()

        self._records[cfg["run_id"]] = record
        self._active = record
        self._task = asyncio.create_task(_run())
        return record

    async def approver(self, decision: AgentDecision) -> bool:
        """The ApproverFn handed to run_agent."""
        approval_id = None
        try:
            approval_id = decision.get("_approval_id")  # type: ignore[union-attr]
        except Exception:
            approval_id = None
        if not approval_id:
            try:
                approval_id = uuid4().hex
                decision["_approval_id"] = approval_id  # type: ignore[index]
            except Exception:
                approval_id = uuid4().hex
        try:
            loop = asyncio.get_running_loop()
            fut = loop.create_future()
        except Exception:
            return False
        self._pending = (approval_id, fut)
        # Expose pending approval on the active record.
        try:
            if self._active is not None:
                self._active.pending_approval = dict(decision)
        except Exception:
            pass
        try:
            return bool(await fut)
        finally:
            self._pending = None
            try:
                if self._active is not None:
                    self._active.pending_approval = None
            except Exception:
                pass

    def resolve_approval(self, approval_id: str, approved: bool) -> bool:
        """Resolve the pending approval future. Returns False when no match."""
        if self._pending is None:
            return False
        pid, fut = self._pending
        if pid != approval_id or fut.done():
            return False
        try:
            fut.set_result(bool(approved))
        except Exception:
            return False
        return True


REGISTRY: RunRegistry = RunRegistry()
"""Process-wide singleton, created at import."""
