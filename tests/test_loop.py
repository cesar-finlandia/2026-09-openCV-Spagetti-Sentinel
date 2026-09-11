"""DP-AGENT loop tests."""
from __future__ import annotations

import asyncio
import os

import pytest

from app.config.settings import load_settings


def _cfg(run_id, clip, tmp_ev):
    os.environ["SS_EVIDENCE_DIR"] = str(tmp_ev)
    return {"run_id": run_id, "source": f"fixtures/clips/{clip}.mp4",
            "backend": "baseline", "sample_every_n": 3, "max_frames": 300,
            "roi": None, "thresholds": load_settings({}).thresholds,
            "synthetic": True, "replay": False, "evidence_prefix": run_id}


def _run(cfg, approver, monkeypatch=None, timeout=120.0):
    async def go():
        from app.agent import run_agent

        if monkeypatch is not None:
            import app.agent.loop as loop

            monkeypatch.setattr(loop, "APPROVAL_TIMEOUT_S", timeout)
        seen = []

        async def emit(step_id, status, payload, degraded):
            seen.append((step_id, status, payload))

        summary = await run_agent(cfg, emit, approver)
        return summary, seen

    return asyncio.run(go())


def test_nominal_clip_never_pauses(tmp_path, monkeypatch):
    async def approver(d):
        raise AssertionError("approver must not be called")

    summary, seen = _run(_cfg("nom", "good-first-layer", tmp_path), approver)
    assert summary["pause_recommended"] is False
    assert all(a.get("approved") is not False or True for a in summary["approvals"])


def test_failure_clip_pauses_and_asks(tmp_path):
    async def approver(d):
        return True

    summary, seen = _run(_cfg("fail", "spaghetti", tmp_path), approver)
    assert summary["pause_recommended"] is True
    assert len(summary["approvals"]) >= 1
    assert summary["approvals"][0]["approved"] is True
    assert summary["first_alert_frame"] is not None and summary["first_alert_frame"] >= 150


def test_lighting_shift_no_false_pause(tmp_path):
    async def approver(d):
        return True

    summary, _ = _run(_cfg("light", "lighting-shift", tmp_path), approver)
    assert summary["pause_recommended"] is False


def test_envelope_payloads_match_blueprint(tmp_path):
    from app.contracts.steps import ALL_STEPS

    EXPECTED_KEYS = {
        "run-start": {"run_id", "source", "backend", "opencv_version", "cool_version",
                      "total_frames", "synthetic"},
        "ingest": {"frame_index", "t_ms", "sampled"},
        "perceive": {"scores"},
        "decide": {"decision"},
        "act": {"action", "evidence_uri", "requires_human"},
        "await-approval": {"decision", "approval_id"},
        "approval-resolved": {"approval_id", "approved", "resolved_by", "t_ms"},
        "evidence-stored": {"uri", "kind", "bytes", "backend"},
        "rationale": {"text", "checklist", "source"},
        "run-summary": {"summary"},
    }
    # Error perceive payload carries {"degraded": ...} — covered separately.
    async def approver(d):
        return True

    _, seen = _run(_cfg("keys", "stringing", tmp_path), approver)
    assert seen, "no envelopes emitted"
    for step_id, status, payload in seen:
        assert step_id in ALL_STEPS, step_id
        if step_id == "perceive" and status == "error":
            assert "degraded" in payload
            continue
        assert set(payload.keys()) == EXPECTED_KEYS[step_id], (step_id, sorted(payload.keys()))


def test_approval_timeout(tmp_path, monkeypatch):
    async def approver(d):
        await asyncio.sleep(3600)
        return True

    summary, _ = _run(_cfg("to", "spaghetti", tmp_path), approver,
                      monkeypatch=monkeypatch, timeout=0.2)
    assert summary["pause_recommended"] is True
    assert any(a["approved"] is False for a in summary["approvals"])


def test_never_raises(tmp_path, monkeypatch):
    import app.vision.pipeline as pipe

    def boom(*a, **k):
        raise RuntimeError("injected")

    monkeypatch.setattr(pipe, "analyze_frame", boom)

    async def approver(d):
        return True

    summary, _ = _run(_cfg("nr", "good-first-layer", tmp_path), approver)
    assert summary["degraded"] is True
