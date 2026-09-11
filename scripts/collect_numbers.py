"""Collect every quotable figure from the generated artefacts into one dict.

The single reason this exists: no number in any document is retyped by hand. Every figure in
README.md, docs/technical-report.md and both addenda comes from here, so a re-run of the
benchmark or the evaluation cannot leave a stale number in a document.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SOURCES: dict[str, str] = {
    "bench": "bench/results/cool-vs-baseline.json",
    "eval": "eval/results/eval-report.json",
    "deploy": "deploy/deployment-record.json",
    "fixtures": "fixtures/manifest.json",
    "manifest": "assembly.manifest.json",
}


def _read(path: str) -> tuple[Any | None, str | None]:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh), None
    except Exception as err:
        return None, f"{path}: {type(err).__name__}"


def collect() -> dict[str, Any]:
    """Read every source and return the flattened figure set. Never raises."""
    figs: dict[str, Any] = {}
    missing: list[str] = []
    docs: dict[str, Any] = {}
    for key, path in SOURCES.items():
        doc, err = _read(path)
        if doc is None:
            missing.append(path)
            docs[key] = {"_missing": path}
        else:
            docs[key] = doc

    def put(name: str, value: Any, source: str) -> None:
        figs[name] = value
        figs[name + "_source"] = source

    bench, ev, dep, fix = docs["bench"], docs["eval"], docs["deploy"], docs["fixtures"]

    put("deployed_url", dep.get("url"), SOURCES["deploy"])
    put("build_marker", dep.get("build_marker"), SOURCES["deploy"])
    for k in ("instance_type", "arch", "ami_id", "image_digest", "region"):
        put(k, dep.get(k), SOURCES["deploy"])
    for k in ("opencv_version", "cool_version", "cool_installed"):
        put(k, dep.get(k), SOURCES["deploy"])

    be = bench.get("backends", {})
    comp = bench.get("comparison", {})
    put("cool_p95_ms", be.get("cool", {}).get("e2e_ms", {}).get("p95"), SOURCES["bench"])
    put("baseline_p95_ms", be.get("baseline", {}).get("e2e_ms", {}).get("p95"), SOURCES["bench"])
    put("e2e_p95_speedup", comp.get("e2e_p95_speedup"), SOURCES["bench"])
    put("cool_fps", be.get("cool", {}).get("fps"), SOURCES["bench"])
    put("baseline_fps", be.get("baseline", {}).get("fps"), SOURCES["bench"])
    put("fps_speedup", comp.get("fps_speedup"), SOURCES["bench"])
    put("cool_usd_per_1000", be.get("cool", {}).get("usd_per_1000_frames"), SOURCES["bench"])
    put("baseline_usd_per_1000", be.get("baseline", {}).get("usd_per_1000_frames"), SOURCES["bench"])
    put("cost_reduction_pct", comp.get("cost_reduction_pct"), SOURCES["bench"])
    put("accelerated_ops", be.get("cool", {}).get("accelerated_ops"), SOURCES["bench"])
    put("core_workload_share_pct", comp.get("core_workload_share_pct"), SOURCES["bench"])
    put("scores_identical", bench.get("scores_identical"), SOURCES["bench"])

    cases = ev.get("cases", [])
    put("eval_passed", sum(1 for c in cases if c.get("passed")), SOURCES["eval"])
    put("eval_total", len([c for c in cases if not c.get("skipped")]), SOURCES["eval"])
    put("eval_axes", ev.get("axes"), SOURCES["eval"])
    fail = next((c for c in cases if c["id"] == "failure-pauses-and-asks"), {})
    put("detect_latency_frames", fail.get("observed", {}).get("detect_latency_frames"),
        SOURCES["eval"])
    put("detect_latency_s", fail.get("observed", {}).get("detect_latency_s"), SOURCES["eval"])
    flip = next((c for c in cases if c["id"] == "threshold-flip-changes-action"), {})
    put("action_below", flip.get("observed", {}).get("action_below"), SOURCES["eval"])
    put("action_above", flip.get("observed", {}).get("action_above"), SOURCES["eval"])
    put("delta_in_score", flip.get("observed", {}).get("delta_in_score"), SOURCES["eval"])
    put("limitations", ev.get("limitations"), SOURCES["eval"])

    put("fixture_count", len(fix.get("clips", [])), SOURCES["fixtures"])
    put("fixture_ids", [c.get("id") for c in fix.get("clips", [])], SOURCES["fixtures"])
    put("synthetic", fix.get("synthetic"), SOURCES["fixtures"])

    figs["missing"] = missing
    try:
        figs["authoritative"] = bool(bench.get("authoritative"))
    except Exception:
        figs["authoritative"] = False
    return figs


def render_table(figures: dict[str, Any], keys: list[str]) -> str:
    """Markdown table of `keys` with their values and their source file."""
    L = ["| figure | value | source |", "|---|---|---|"]
    for k in keys:
        L.append(f"| {k} | {figures.get(k)} | {figures.get(k + '_source', '')} |")
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Collect quotable figures")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    figs = collect()
    if args.json:
        print(json.dumps(figs, indent=2, default=str))
    else:
        for k in sorted(figs):
            if not k.endswith("_source") and k != "missing":
                print(f"{k} = {figs[k]}")
        if figs["missing"]:
            print(f"missing: {figs['missing']}")
    if args.check:
        if figs["missing"] or not figs.get("authoritative"):
            if figs["missing"]:
                print(f"collect_numbers: missing sources: {figs['missing']}")
            if not figs.get("authoritative"):
                print("collect_numbers: bench.authoritative is false")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
