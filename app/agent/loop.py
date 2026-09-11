"""run_agent() — the perception→decision→action loop. REQ-F05/F08."""
from __future__ import annotations

import asyncio
import collections
import logging
import math
import os
import statistics
import time
from datetime import datetime, timezone
from typing import Awaitable, Callable
from uuid import uuid4

from app.agent.policy import decide
from app.agent.tools import call_tool, clear_tool_context, set_tool_context
from app.agent.trace import TraceRecorder
from app.contracts.steps import (
    STEP_ACT, STEP_APPROVAL_RESOLVED, STEP_AWAIT_APPROVAL, STEP_DECIDE,
    STEP_EVIDENCE_STORED, STEP_INGEST, STEP_PERCEIVE, STEP_RATIONALE,
    STEP_RUN_START, STEP_RUN_SUMMARY,
)
from app.contracts.types import AgentDecision, RunSummary, RunConfig

logger = logging.getLogger("agent.loop")

EmitFn = Callable[[str, str, dict, bool], Awaitable[None]]
ApproverFn = Callable[[AgentDecision], Awaitable[bool]]

EVIDENCE_WINDOW: int = 30
APPROVAL_TIMEOUT_S: float = 120.0


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _fixture_id_from(cfg: RunConfig) -> str:
    src = cfg.get("source", "")
    base = os.path.basename(src.replace("\\", "/"))
    return os.path.splitext(base)[0]


def _nearest_p(xs: list[float], q: float) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    idx = min(len(s) - 1, max(0, math.ceil(q * len(s)) - 1))
    return float(s[idx])


async def run_agent(cfg: RunConfig, emit: EmitFn, approver: ApproverFn) -> RunSummary:
    """Run one complete analysis session and return its RunSummary. Never raises."""
    from app.config.settings import load_settings

    t_start = time.perf_counter()
    settings = load_settings()
    trace = TraceRecorder(cfg.get("run_id", "run"))
    history: list = []
    decisions: list[AgentDecision] = []
    approvals: list = []
    evidence_uris: list[str] = []
    ring: collections.deque = collections.deque(maxlen=EVIDENCE_WINDOW)
    frame_times: list[float] = []
    frame_errors = 0
    try:
        from app.evidence import create_evidence_store
        from app.vision import (
            backend_info, create_pipeline_state, get_backend, iter_frames,
        )

        store = create_evidence_store(settings)
        backend = get_backend(cfg.get("backend", "baseline"))
        try:
            backend.reset_state()
        except Exception:
            pass
        state = create_pipeline_state(cfg)
        info = backend_info(backend)
        await emit(STEP_RUN_START, "started",
                   {"run_id": cfg["run_id"], "source": cfg["source"],
                    "backend": info["name"], "opencv_version": info["opencv_version"],
                    "cool_version": info["cool_version"], "total_frames": None,
                    "synthetic": cfg.get("synthetic", False)}, False)
        set_tool_context({"backend": backend, "state": state, "cfg": cfg, "frame": None,
                          "ring": ring, "store": store, "history": history})

        # Replay branch.
        pairs: list[tuple] = []
        use_replay = False
        if cfg.get("replay"):
            try:
                from app.fixtures import replay_scores

                cached = replay_scores(_fixture_id_from(cfg), cache_dir=settings.cache_dir)
                if cached:
                    use_replay = True
                    pairs = [(s, None) for s in cached]
            except Exception:
                pairs = []

        async def _process(idx: int, t_ms: int, frame: Any) -> None:
            nonlocal frame_errors
            from app.vision import pipeline as _pipeline  # noqa: F401 (patch target note)
            f0 = time.perf_counter()
            res = call_tool("score_frame", {"frame_index": idx, "t_ms": t_ms})
            tool_out = {k: v for k, v in res.items() if k not in ("scores",)}
            trace.record("tool_call", STEP_PERCEIVE, t_ms,
                         {"frame_index": idx, "t_ms": t_ms}, tool_out, tool="score_frame")
            if "error" in res:
                frame_errors += 1
                try:
                    from src.resilience.degraded import make_degraded_result
                except Exception:
                    from src.resilience import make_degraded_result  # type: ignore
                await emit(STEP_PERCEIVE, "error",
                           {"degraded": make_degraded_result(
                               reason="score_frame_failed", fallback_source="none",
                               original_error=str(res.get("error")))}, True)
                return
            scores = res["scores"]
            await emit(STEP_PERCEIVE, "done", {"scores": scores}, bool(scores.get("degraded")))
            trace.record("perception", STEP_PERCEIVE, t_ms,
                         {"frame_index": idx}, {"scores": scores})
            decision = decide(scores, history, cfg)
            trace.record("decision", STEP_DECIDE, t_ms,
                         {"scores": scores}, {"decision": decision})
            history.append(scores)
            if decision["action"] != "continue":
                try:
                    from app.rationale import explain

                    r = await explain(decision, scores, history, cfg)
                    decision["rationale"] = r.get("text", "")
                    decision["checklist"] = list(r.get("checklist", []))
                    decision["rationale_source"] = r.get("source", "fallback")
                    await emit(STEP_RATIONALE, "done",
                               {"text": r.get("text", ""), "checklist": r.get("checklist", []),
                                "source": r.get("source", "fallback")}, bool(r.get("degraded")))
                except Exception as err:
                    logger.warning("agent: rationale failed (%s)", type(err).__name__)
            await emit(STEP_DECIDE, "done", {"decision": decision},
                       bool(decision.get("degraded")))
            # Action dispatch.
            if decision["action"] == "capture_evidence":
                ev = call_tool("capture_evidence", {"frame_index": idx})
                decision["evidence_uri"] = ev.get("evidence_uri")
                if ev.get("evidence_uri"):
                    evidence_uris.append(ev["evidence_uri"])
                trace.record("tool_call", STEP_EVIDENCE_STORED, t_ms,
                             {"frame_index": idx}, {k: v for k, v in ev.items()
                                                    if k != "_tool"}, tool="capture_evidence")
                await emit(STEP_EVIDENCE_STORED, "done",
                           {"uri": ev.get("evidence_uri") or "", "kind": "clip",
                            "bytes": ev.get("bytes", 0), "backend": ev.get("backend", "local")},
                           bool(ev.get("degraded")))
            elif decision["action"] == "request_pause_approval":
                ev = call_tool("capture_evidence", {"frame_index": idx})
                decision["evidence_uri"] = ev.get("evidence_uri")
                if ev.get("evidence_uri"):
                    evidence_uris.append(ev["evidence_uri"])
                trace.record("tool_call", STEP_EVIDENCE_STORED, t_ms,
                             {"frame_index": idx}, {k: v for k, v in ev.items()
                                                    if k != "_tool"}, tool="capture_evidence")
                await emit(STEP_EVIDENCE_STORED, "done",
                           {"uri": ev.get("evidence_uri") or "", "kind": "clip",
                            "bytes": ev.get("bytes", 0), "backend": ev.get("backend", "local")},
                           bool(ev.get("degraded")))
                approval_id = uuid4().hex
                try:
                    decision["_approval_id"] = approval_id
                except Exception:
                    pass
                record = {"approval_id": approval_id, "run_id": cfg["run_id"],
                          "frame_index": idx, "approved": None,
                          "created_at": _utcnow_iso(), "resolved_at": None}
                approvals.append(record)
                await emit(STEP_AWAIT_APPROVAL, "started",
                           {"decision": decision, "approval_id": approval_id}, False)
                try:
                    approved = await asyncio.wait_for(approver(decision),
                                                      timeout=APPROVAL_TIMEOUT_S)
                except asyncio.TimeoutError:
                    approved = False
                except Exception:
                    approved = False
                record["approved"] = bool(approved)
                record["resolved_at"] = _utcnow_iso()
                try:
                    del decision["_approval_id"]
                except Exception:
                    pass
                await emit(STEP_APPROVAL_RESOLVED, "done",
                           {"approval_id": approval_id, "approved": bool(approved),
                            "resolved_by": "human", "t_ms": t_ms}, False)
            await emit(STEP_ACT, "done",
                       {"action": decision["action"],
                        "evidence_uri": decision["evidence_uri"],
                        "requires_human": decision["requires_human"]}, False)
            trace.record("action", STEP_ACT, t_ms, {"decision": decision},
                         {"performed": decision["action"],
                          "evidence_uri": decision["evidence_uri"]})
            decisions.append(decision)
            frame_times.append((time.perf_counter() - f0) * 1000.0)

        if use_replay:
            trace2 = TraceRecorder(cfg.get("run_id", "run"))
            for scores in [p[0] for p in pairs]:
                f0 = time.perf_counter()
                trace2.record("perception", STEP_PERCEIVE, int(scores["t_ms"]),
                              {"frame_index": scores["frame_index"]}, {"scores": scores})
                await emit(STEP_PERCEIVE, "done", {"scores": scores},
                           bool(scores.get("degraded")))
                decision = decide(scores, history, cfg)
                trace2.record("decision", STEP_DECIDE, int(scores["t_ms"]),
                              {"scores": scores}, {"decision": decision})
                history.append(scores)
                if decision["action"] != "continue":
                    try:
                        from app.rationale import explain

                        r = await explain(decision, scores, history, cfg)
                        decision["rationale"] = r.get("text", "")
                        decision["checklist"] = list(r.get("checklist", []))
                        decision["rationale_source"] = r.get("source", "fallback")
                        await emit(STEP_RATIONALE, "done",
                                   {"text": r.get("text", ""), "checklist": r.get("checklist", []),
                                    "source": r.get("source", "fallback")},
                                   bool(r.get("degraded")))
                    except Exception:
                        pass
                await emit(STEP_DECIDE, "done", {"decision": decision},
                           bool(decision.get("degraded")))
                if decision["action"] in ("capture_evidence", "request_pause_approval"):
                    ev = call_tool("capture_evidence", {"frame_index": int(scores["frame_index"])})
                    decision["evidence_uri"] = ev.get("evidence_uri")
                    if ev.get("evidence_uri"):
                        evidence_uris.append(ev["evidence_uri"])
                    trace2.record("tool_call", STEP_EVIDENCE_STORED, int(scores["t_ms"]),
                                  {"frame_index": scores["frame_index"]}, {},
                                  tool="capture_evidence")
                    await emit(STEP_EVIDENCE_STORED, "done",
                               {"uri": ev.get("evidence_uri") or "", "kind": "clip",
                                "bytes": ev.get("bytes", 0),
                                "backend": ev.get("backend", "local")},
                               bool(ev.get("degraded")))
                    if decision["action"] == "request_pause_approval":
                        approval_id = uuid4().hex
                        try:
                            decision["_approval_id"] = approval_id
                        except Exception:
                            pass
                        record = {"approval_id": approval_id, "run_id": cfg["run_id"],
                                  "frame_index": int(scores["frame_index"]), "approved": None,
                                  "created_at": _utcnow_iso(), "resolved_at": None}
                        approvals.append(record)
                        await emit(STEP_AWAIT_APPROVAL, "started",
                                   {"decision": decision, "approval_id": approval_id}, False)
                        try:
                            approved = await asyncio.wait_for(
                                approver(decision), timeout=APPROVAL_TIMEOUT_S)
                        except Exception:
                            approved = False
                        record["approved"] = bool(approved)
                        record["resolved_at"] = _utcnow_iso()
                        try:
                            del decision["_approval_id"]
                        except Exception:
                            pass
                        await emit(STEP_APPROVAL_RESOLVED, "done",
                                   {"approval_id": approval_id, "approved": bool(approved),
                                    "resolved_by": "human", "t_ms": int(scores["t_ms"])}, False)
                await emit(STEP_ACT, "done",
                           {"action": decision["action"],
                            "evidence_uri": decision["evidence_uri"],
                            "requires_human": decision["requires_human"]}, False)
                trace2.record("action", STEP_ACT, int(scores["t_ms"]), {"decision": decision},
                              {"performed": decision["action"],
                               "evidence_uri": decision["evidence_uri"]})
                decisions.append(decision)
                frame_times.append((time.perf_counter() - f0) * 1000.0)
            trace = trace2
        else:
            for idx, t_ms, frame in iter_frames(cfg["source"], cfg):
                ring.append(frame)
                from app.agent.tools import _CONTEXT

                _CONTEXT["frame"] = frame
                await emit(STEP_INGEST, "streaming",
                           {"frame_index": idx, "t_ms": t_ms, "sampled": True}, False)
                await _process(idx, t_ms, frame)
        clear_tool_context()
        wall_ms = int((time.perf_counter() - t_start) * 1000)
        frames_sampled = len(frame_times)
        try:
            frames_processed = frames_sampled * int(cfg.get("sample_every_n", 1))
        except Exception:
            frames_processed = frames_sampled
        fps = round(frames_processed / max(1e-6, wall_ms / 1000.0), 2)
        p50 = _nearest_p(frame_times, 0.50)
        p95 = _nearest_p(frame_times, 0.95)
        first = next((d for d in decisions if d["action"] != "continue"), None)
        summary: RunSummary = {
            "run_id": cfg["run_id"], "backend": info["name"],
            "frames_processed": frames_processed, "frames_sampled": frames_sampled,
            "wall_ms": wall_ms, "fps": fps, "p50_frame_ms": p50, "p95_frame_ms": p95,
            "decisions": decisions,
            "first_alert_frame": first["frame_index"] if first else None,
            "first_alert_t_ms": first["t_ms"] if first else None,
            "pause_recommended": any(d["action"] == "request_pause_approval" for d in decisions),
            "approvals": approvals, "evidence_uris": evidence_uris,
            "degraded": bool(frame_errors) or any(bool(d.get("degraded")) for d in decisions),
            "synthetic": bool(cfg.get("synthetic", False)),
            "build_marker": settings.build_marker,
        }
        try:
            store.put_json(cfg["run_id"], "summary", dict(summary))
            trace.write(os.path.join(settings.evidence_dir, "runs", cfg["run_id"], "trace.jsonl"))
            store.put_json(cfg["run_id"], "trace",
                           {"steps": trace.steps(), "summary": trace.summary()})
        except Exception as err:
            logger.warning("agent: summary persist failed (%s)", type(err).__name__)
        await emit(STEP_RUN_SUMMARY, "done", {"summary": summary},
                   bool(summary["degraded"]))
        return summary
    except Exception as err:
        logger.error("agent: run failed (%s)", type(err).__name__)
        try:
            clear_tool_context()
        except Exception:
            pass
        try:
            from src.resilience.degraded import make_degraded_result
        except Exception:
            from src.resilience import make_degraded_result  # type: ignore
        try:
            await emit(STEP_RUN_SUMMARY, "error",
                       {"degraded": make_degraded_result(
                           reason="run_failed", fallback_source="none",
                           original_error=f"{type(err).__name__}")}, True)
        except Exception:
            pass
        return {
            "run_id": cfg.get("run_id", "run"),
            "backend": cfg.get("backend", "baseline"),
            "frames_processed": 0, "frames_sampled": len(frame_times),
            "wall_ms": int((time.perf_counter() - t_start) * 1000),
            "fps": 0.0, "p50_frame_ms": 0.0, "p95_frame_ms": 0.0,
            "decisions": decisions,
            "first_alert_frame": None, "first_alert_t_ms": None,
            "pause_recommended": False, "approvals": approvals,
            "evidence_uris": evidence_uris, "degraded": True,
            "synthetic": bool(cfg.get("synthetic", False)),
            "build_marker": settings.build_marker,
        }
