"""DP-COOL-BENCH tests — report shape and honesty guards."""
from __future__ import annotations

import importlib.util
import json
import os
import platform
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORT = os.path.join(REPO, "bench", "results", "cool-vs-baseline.json")
MARKDOWN = os.path.join(REPO, "bench", "results", "cool-vs-baseline.md")


def _load_bench():
    spec = importlib.util.spec_from_file_location(
        "run_bench", os.path.join(REPO, "bench", "run_bench.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _report():
    assert os.path.exists(REPORT), "run bench/run_bench.py --allow-non-graviton first"
    return json.load(open(REPORT, encoding="utf-8"))


def test_report_shape():
    r = _report()
    assert r["schema"] == "cool-vs-baseline/1.0.0"
    for key in ("authoritative", "generated_at", "host", "versions", "params",
                "backends", "comparison", "scores_identical", "notes"):
        assert key in r, key
    for b in ("cool", "baseline"):
        for key in ("accelerated_ops", "frames", "e2e_ms", "fps",
                    "cpu_utilisation_pct", "per_op_ms", "usd_per_1000_frames"):
            assert key in r["backends"][b], (b, key)
    for key in ("e2e_p95_speedup", "fps_speedup", "cost_reduction_pct",
                "per_op_speedup", "cool_executed_core_workload",
                "core_workload_share_pct"):
        assert key in r["comparison"], key
    assert isinstance(r["authoritative"], bool)


def test_non_authoritative_flag():
    r = _report()
    if platform.machine() != "aarch64":
        assert r["authoritative"] is False
        assert any("non-authoritative" in n or "COOL build not present" in n
                   for n in r["notes"]), r["notes"]


def test_scores_identical_on_same_backend(tmp_path):
    m = _load_bench()
    out = str(tmp_path / "out")
    code = subprocess.run(
        [sys.executable, os.path.join(REPO, "bench", "run_bench.py"),
         "--clips", "good-first-layer", "--repeats", "1", "--warmup", "0",
         "--backends", "baseline,baseline", "--allow-non-graviton", "--out", out],
        capture_output=True, text=True, cwd=REPO).returncode
    assert code == 0
    r = json.load(open(os.path.join(out, "cool-vs-baseline.json"), encoding="utf-8"))
    assert r["scores_identical"] is True


def test_speedups_withheld_when_scores_differ():
    m = _load_bench()
    # Exercise the comparison branch directly: mismatched scores withhold speedups.
    same, _ = m._scores_equal(
        [{"frame_index": 0, "spaghetti_score": 0.1, "ops_ms": {}}],
        [{"frame_index": 0, "spaghetti_score": 0.9, "ops_ms": {}}])
    assert same is False
    # And the summarise edge cases from WU-01.
    s = m.summarise([1.0, 2.0, 3.0, 4.0, 100.0])
    assert (s["p50"], s["p95"]) == (3.0, 100.0)
    assert m.summarise([]) == {"p50": 0.0, "p95": 0.0, "mean": 0.0, "stdev": 0.0}
    assert m.usd_per_1000_frames(0.0, 0.145) == 0.0


def test_cost_is_labelled_modelled():
    assert os.path.exists(MARKDOWN)
    md = open(MARKDOWN, encoding="utf-8").read()
    assert "MODELLED" in md
