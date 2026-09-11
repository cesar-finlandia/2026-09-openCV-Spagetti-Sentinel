"""DP-EVIDENCE tests — REQ-N01 / REQ-N07."""
from __future__ import annotations

import json
import logging
import os


def _settings(tmpdir):
    from app.config.settings import load_settings

    return load_settings({"S3_BUCKET": "", "SS_EVIDENCE_DIR": str(tmpdir)})


def test_local_roundtrip(tmp_path):
    import numpy as np

    from app.evidence import create_evidence_store

    s = create_evidence_store(_settings(str(tmp_path)))
    frames = [np.full((240, 320, 3), i, np.uint8) for i in range(20)]
    c = s.put_clip("r1", frames, {"frame_index": 150})
    f = s.put_frame("r1", frames[0], {"frame_index": 150})
    j = s.put_json("r1", "decision", {"action": "request_pause_approval"})
    assert c["key"] == "runs/r1/clip-000150.mp4" and c["bytes"] > 0
    assert f["key"] == "runs/r1/frame-000150.png" and f["bytes"] > 0
    assert j["key"] == "runs/r1/decision.json"
    assert json.load(open(os.path.join(str(tmp_path), j["key"])))["action"] == "request_pause_approval"


def test_empty_clip_degrades(tmp_path):
    from app.evidence import create_evidence_store

    s = create_evidence_store(_settings(str(tmp_path)))
    r = s.put_clip("r1", [], {"frame_index": 0})
    assert r["degraded"] is True and r["bytes"] == 0


def test_readonly_root_degrades(tmp_path):
    import sys

    if sys.platform.startswith("win"):
        # Simulate with a file-as-dir: local_root points inside a file path.
        from app.evidence import create_evidence_store

        blocker = tmp_path / "blocker"
        blocker.write_bytes(b"x")
        s = create_evidence_store(_settings(str(blocker / "sub")))
        r = s.put_json("r1", "decision", {"a": 1})
        assert r["degraded"] is True and r["uri"] == ""
        return
    from app.evidence import create_evidence_store

    d = tmp_path / "ro"
    d.mkdir()
    os.chmod(d, 0o500)
    try:
        s = create_evidence_store(_settings(str(d / "sub")))
        # Make parent read-only so makedirs fails.
        r = s.put_json("r1", "decision", {"a": 1})
        # Either degraded (strict) or written (root running) — never raises.
        assert isinstance(r["degraded"], bool)
    finally:
        os.chmod(d, 0o700)


def test_s3_failure_falls_back_to_local(tmp_path, monkeypatch, caplog):
    from app.evidence import create_evidence_store

    s = create_evidence_store(_settings(str(tmp_path)))

    class Boom:
        def put_object(self, **kw):
            raise RuntimeError("boom")

    s._client = Boom()
    s.backend = "s3"
    s.bucket = "test-bucket"
    # Rebuild uploader to use the boom client.
    from app.evidence import store as st

    def boom_raw(key, data, ct):
        return s._raw_upload(key, data, ct)

    s._raw_upload = boom_raw.__get__(s, type(s)) if hasattr(boom_raw, "__get__") else boom_raw
    with caplog.at_level(logging.DEBUG):
        r = s.put_json("r1", "decision", {"a": 1})
    assert r["degraded"] is True
    assert os.path.exists(os.path.join(str(tmp_path), r["key"]))
    for rec in caplog.records:
        msg = rec.getMessage()
        assert "AKIA" not in msg and "aws_secret" not in msg
        assert "Signature=" not in msg and "boom" not in msg


def test_no_secret_in_logs(tmp_path, caplog):
    test_s3_failure_falls_back_to_local(tmp_path, __import__("pytest").MonkeyPatch(), caplog)


def test_key_sanitisation(tmp_path):
    import re

    from app.evidence import create_evidence_store

    s = create_evidence_store(_settings(str(tmp_path)))
    r = s.put_json("r1", "../../etc/passwd", {})
    assert re.match(r"^runs/r1/[-\w.]+\.json$", r["key"]), r["key"]
