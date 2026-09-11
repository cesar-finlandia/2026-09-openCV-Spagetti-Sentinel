"""DP-EVAL tests — report shape, limitations, axes, strict gate."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORT = os.path.join(REPO, "eval", "results", "eval-report.json")
MARKDOWN = os.path.join(REPO, "eval", "results", "eval-report.md")


def _report():
    assert os.path.exists(REPORT), "run python eval/run_eval.py --out eval/results first"
    return json.load(open(REPORT, encoding="utf-8"))


def _mod():
    spec = importlib.util.spec_from_file_location(
        "run_eval", os.path.join(REPO, "eval", "run_eval.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_report_shape():
    r = _report()
    assert r["schema"] == "spaghetti-sentinel-eval-report/1.0.0"
    for key in ("generated_at", "environment", "axes", "cases",
                "failure_cases", "limitations"):
        assert key in r, key
    for c in r["cases"]:
        for key in ("id", "kind", "axis", "passed", "skipped",
                    "observed", "expected", "asks"):
            assert key in c, (c.get("id"), key)
    for axis in ("task_effectiveness", "failure_handling",
                 "observability", "human_control"):
        assert axis in r["axes"], axis


def test_limitations_never_empty():
    r = _report()
    assert len(r["limitations"]) >= 5
    md = open(MARKDOWN, encoding="utf-8").read()
    assert "## Failure cases and limitations" in md
    assert len(md.split("## Failure cases and limitations")[1].strip()) > 100


def test_severity_order():
    m = _mod()
    assert [m.SEVERITY[a] for a in
            ("continue", "nudge_parameters", "capture_evidence",
             "request_pause_approval")] == [0, 1, 2, 3]


def test_threshold_flip_case_passes():
    m = _mod()
    assert m.check_threshold_flip()["passed"] is True


def test_every_case_has_an_axis():
    m = _mod()
    cases = json.load(open(os.path.join(REPO, "eval", "cases.json"),
                           encoding="utf-8"))["cases"]
    for c in cases:
        assert c["id"] in m.AXES, c["id"]


def test_strict_exit_code(tmp_path):
    cases = {"schema": "x", "cases": [{
        "id": "impossible", "clip": "good-first-layer", "kind": "synthetic",
        "expect": {"pause_recommended": True}, "asks": "impossible"}]}
    p = os.path.join(str(tmp_path), "cases.json")
    json.dump(cases, open(p, "w"))
    # AXES has no "impossible" id; run_case still executes (axis defaults).
    r1 = subprocess.run(
        [sys.executable, os.path.join(REPO, "eval", "run_eval.py"),
         "--cases", p, "--out", str(tmp_path), "--strict"],
        capture_output=True, text=True, cwd=REPO)
    r0 = subprocess.run(
        [sys.executable, os.path.join(REPO, "eval", "run_eval.py"),
         "--cases", p, "--out", str(tmp_path)],
        capture_output=True, text=True, cwd=REPO)
    assert r1.returncode == 1, r1.stdout[-500:]
    assert r0.returncode == 0


def test_every_decision_has_a_measurement():
    r = _report()
    assert r["observability_checks"]["traceable"] is True


def test_tool_calls_precede_decisions():
    r = _report()
    assert r["observability_checks"]["tools_recorded"] is True
    assert r["observability_checks"]["tools_known"] is True
