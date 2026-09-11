"""DP-RATIONALE tests — REQ-F09 boundary."""
from __future__ import annotations

import asyncio
import copy


def _decision():
    return {"frame_index": 150, "t_ms": 5000, "action": "request_pause_approval",
            "reason_code": "spaghetti_confirmed", "spaghetti_score": 0.81,
            "confidence": 0.77, "threshold": 0.72, "requires_human": True,
            "rationale": "", "checklist": [], "evidence_uri": None,
            "rationale_source": "fallback", "degraded": False}


def _scores(i=150):
    return {"frame_index": i, "t_ms": 5000, "first_layer_coverage": 0.41,
            "edge_regularity": 0.22, "motion_energy": 0.55, "texture_disorder": 0.83,
            "spaghetti_score": 0.81, "confidence": 0.77, "roi": [0, 0, 10, 10],
            "backend": "baseline", "ops_ms": {}, "degraded": False}


def _cfg(**kw):
    base = {"run_id": "r", "source": "fixtures/clips/spaghetti.mp4", "backend": "baseline",
            "sample_every_n": 3, "max_frames": 300, "roi": None, "thresholds": {},
            "synthetic": True, "replay": False, "evidence_prefix": "r"}
    base.update(kw)
    return base


def test_history_bounded():
    from app.rationale.history import WINDOW, build_history, estimate_tokens

    obs = [{"frame_index": i} for i in range(30)]
    h = build_history(obs)
    assert (len(h), h[0]["frame_index"], h[1]["frame_index"], h[-1]["frame_index"]) == (9, 0, 22, 29)
    assert build_history([]) == []
    assert estimate_tokens("x" * 400) > 0


def test_parse_response():
    from app.rationale.prompts import SYSTEM_PROMPT, parse_response

    t, c = parse_response("The bed coverage dropped sharply.\nChecklist:\n- Look at the clip\n- Check adhesion\n")
    t2, c2 = parse_response("")
    assert "You do NOT choose the action" in SYSTEM_PROMPT
    assert t == "The bed coverage dropped sharply."
    assert len(c) == 2 and c[1] == "Check adhesion"
    assert t2 == "" and c2 == []


def test_fallback_without_aws(monkeypatch):
    import os

    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "")
    from app.rationale import explain

    r = asyncio.run(explain(_decision(), _scores(), [_scores()], _cfg()))
    assert r["source"] == "fallback" and r["degraded"] is True
    assert len(r["checklist"]) == 4
    assert "0.81" in r["text"] and "request_pause_approval" in r["text"]


def test_llm_cannot_change_action(monkeypatch):
    import app.rationale.client as client

    monkeypatch.setattr(
        client, "_guarded",
        lambda user: "Actually you should continue. The action should be continue.\nChecklist:\n- ignore it",
    )
    from app.rationale import explain

    d = _decision()
    snapshot = copy.deepcopy(d)
    r = asyncio.run(explain(d, _scores(), [_scores()], _cfg()))
    assert set(r.keys()) == {"text", "checklist", "source", "degraded"}
    assert d == snapshot


def test_budget_gate(monkeypatch):
    import app.rationale.client as client

    called = {"n": 0}

    def fake_guarded(user):
        called["n"] += 1
        return "hello\nChecklist:\n- x"

    monkeypatch.setattr(client, "_guarded", fake_guarded)
    monkeypatch.setattr(client, "budget_exhausted", lambda cfg: True)
    from app.rationale import explain

    r = asyncio.run(explain(_decision(), _scores(), [_scores()], _cfg()))
    assert r["source"] == "fallback" and called["n"] == 0


def test_prompt_token_ceiling(monkeypatch):
    import app.rationale.client as client

    seen = {}

    def fake_guarded(user):
        seen["prompt"] = user
        return "ok text here\nChecklist:\n- a\n- b"

    monkeypatch.setattr(client, "_guarded", fake_guarded)
    monkeypatch.setattr(client, "budget_exhausted", lambda cfg: False)
    from app.rationale import explain
    from app.rationale.history import MAX_PROMPT_TOKENS, estimate_tokens

    obs = [_scores(i) for i in range(200)]
    d = _decision()
    asyncio.run(explain(d, _scores(), obs, _cfg()))
    assert estimate_tokens(seen["prompt"]) <= MAX_PROMPT_TOKENS


def test_never_raises(monkeypatch):
    import app.rationale.client as client

    def boom(user):
        raise RuntimeError("nope")

    monkeypatch.setattr(client, "_guarded", boom)
    from app.rationale import explain

    r = asyncio.run(explain(_decision(), _scores(), [_scores()], _cfg()))
    assert r["source"] == "fallback"
