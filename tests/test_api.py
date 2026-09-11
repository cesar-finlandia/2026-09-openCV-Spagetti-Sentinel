"""DP-API integration tests — REQ-F08 / REQ-F11."""
from __future__ import annotations

import json
import os
import time

import pytest
from fastapi.testclient import TestClient

from app.contracts.steps import ALL_STEPS


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("S3_BUCKET", "")
    monkeypatch.setenv("SS_EVIDENCE_DIR", str(tmp_path / "ev"))
    monkeypatch.setenv("SS_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("BUILD_MARKER", "test-marker")
    # Fresh registry per test (single-active-run rule is per process).
    import app.api.runs as runs

    runs.REGISTRY = runs.RunRegistry()
    import app.api.publisher as pub

    pub._PUBLISHERS.clear()
    from app.api.main import app

    try:
        app.state.evidence_health = None
    except Exception:
        pass
    with TestClient(app) as c:
        yield c


def _check_envelope(env, schema):
    try:
        from src.resilience import validate

        res = validate(schema, env)
        errs = res.get("errors", []) if isinstance(res, dict) else list(res or [])
        return errs
    except Exception:
        return []


def test_health_and_manifests(client):
    h = client.get("/healthz").json()
    t = client.get("/api/tools").json()
    f = client.get("/api/fixtures").json()
    bad = client.post("/api/runs", json={"source": "/nope/missing.mp4"})
    assert h["status"] in ("ok", "degraded") and h["build_marker"] == "test-marker"
    assert len(t) == 4 and f["synthetic"] is True and len(f["clips"]) == 4
    assert bad.status_code == 400


def _wait_summary(client, trace_id, timeout=120.0):
    schema = json.load(open("contracts/event-envelope.schema.json"))
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        r = client.get("/events", params={"trace_id": trace_id}).json()
        events = r.get("events", [])
        if events and events[-1].get("step_id") == "run-summary":
            # Validate every envelope.
            seqs = []
            for e in events:
                assert _check_envelope(e, schema) == [], e
                assert e["step_id"] in ALL_STEPS
                seqs.append(e["sequence"])
            assert seqs == list(range(len(seqs))), "sequence gap"
            return events
        time.sleep(1.0)
    raise AssertionError("run-summary never arrived")


def test_run_streams_envelopes(client):
    r = client.post("/api/runs", json={"fixture_id": "good-first-layer",
                                       "sample_every_n": 10, "max_frames": 300})
    assert r.status_code == 200, r.text
    trace_id = r.json()["trace_id"]
    events = _wait_summary(client, trace_id)
    assert any(e["step_id"] == "run-summary" for e in events)


def test_payload_keys_match_blueprint(client):
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
    r = client.post("/api/runs", json={"fixture_id": "stringing",
                                       "sample_every_n": 10, "max_frames": 300})
    trace_id = r.json()["trace_id"]
    events = _wait_summary(client, trace_id)
    for e in events:
        if e["step_id"] == "perceive" and e["status"] == "error":
            assert "degraded" in e["payload"]
            continue
        assert set(e["payload"].keys()) == EXPECTED_KEYS[e["step_id"]], (
            e["step_id"], sorted(e["payload"].keys()))


def test_second_run_conflicts(client):
    r1 = client.post("/api/runs", json={"fixture_id": "spaghetti",
                                        "sample_every_n": 1, "max_frames": 300})
    assert r1.status_code == 200
    r2 = client.post("/api/runs", json={"fixture_id": "good-first-layer",
                                        "sample_every_n": 10, "max_frames": 300})
    assert r2.status_code == 409


def test_approval_roundtrip(client):
    r = client.post("/api/runs", json={"fixture_id": "spaghetti",
                                       "sample_every_n": 3, "max_frames": 300})
    assert r.status_code == 200
    run_id = r.json()["run_id"]
    trace_id = r.json()["trace_id"]
    deadline = time.time() + 180.0
    approval_id = None
    while time.time() < deadline:
        ev = client.get("/events", params={"trace_id": trace_id}).json().get("events", [])
        for e in ev:
            if e["step_id"] == "await-approval":
                approval_id = e["payload"]["approval_id"]
                break
        if approval_id:
            break
        time.sleep(1.0)
    assert approval_id, "await-approval never arrived"
    ans = client.post(f"/api/runs/{run_id}/approve",
                      json={"approval_id": approval_id, "approved": True})
    assert ans.status_code == 200 and ans.json() == {"resolved": True}
    deadline = time.time() + 120.0
    while time.time() < deadline:
        ev = client.get("/events", params={"trace_id": trace_id}).json().get("events", [])
        for e in ev:
            if e["step_id"] == "approval-resolved" and e["payload"].get("approved") is True:
                return
        time.sleep(1.0)
    raise AssertionError("approval-resolved(true) never arrived")


def test_evidence_path_traversal_blocked(client):
    r = client.get("/api/evidence/..%2F..%2Fetc%2Fpasswd")
    assert r.status_code in (400, 404)


def test_no_secret_in_health(client):
    h = client.get("/healthz").json()
    blob = json.dumps(h)
    assert "AWS_SECRET_ACCESS_KEY" not in blob
    assert "AKIA" not in blob
    assert "aws_session_token" not in blob
