"""COOL vs baseline benchmark — REQ-F13 / REQ-N02 / REQ-N06.

Measures the DP-VISION pipeline (via app.vision directly: no HTTP, no agent)
over the DP-FIXTURES clips, once per backend, alternating per repeat, and
writes bench/results/cool-vs-baseline.{json,md}.

The authoritative run happens on the DP-DEPLOY c7g.xlarge instance (WU-04).
A laptop run MUST pass --allow-non-graviton and is marked non-authoritative.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import os
import platform
import statistics
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger("bench")

INSTANCE_HOURLY_USD: dict[str, float] = {
    "c7g.xlarge": 0.145, "c7g.large": 0.0725, "c7g.2xlarge": 0.29,
    "c6i.xlarge": 0.17, "m7g.xlarge": 0.1632,
}
"""On-demand us-east-1 Linux rates, recorded at build time. MODELLED figures."""


def summarise(values: list[float]) -> dict:
    """{"p50", "p95", "mean", "stdev"} by nearest-rank percentile. Empty -> zeros."""
    if not values:
        return {"p50": 0.0, "p95": 0.0, "mean": 0.0, "stdev": 0.0}

    def p(q: float) -> float:
        xs = sorted(values)
        return xs[min(len(xs) - 1, max(0, math.ceil(q * len(xs)) - 1))]

    try:
        mean = statistics.fmean(values)
    except Exception:
        mean = 0.0
    try:
        stdev = statistics.pstdev(values) if len(values) > 1 else 0.0
    except Exception:
        stdev = 0.0
    return {"p50": round(float(p(0.50)), 3), "p95": round(float(p(0.95)), 3),
            "mean": round(float(mean), 3), "stdev": round(float(stdev), 3)}


def usd_per_1000_frames(fps: float, hourly_usd: float) -> float:
    """(1000 / fps) / 3600 * hourly_usd, rounded to 5 decimals. fps <= 0 -> 0.0."""
    try:
        if fps <= 0:
            return 0.0
        return round((1000.0 / fps) / 3600.0 * hourly_usd, 5)
    except Exception:
        return 0.0


def measure_pass(clip_path: str, backend_name: str, cfg: dict) -> dict:
    """One full pass over one clip. Returns frame_ms, ops_ms, scores, cpu_pct."""
    from app.vision import OP_NAMES, analyze_frame, create_pipeline_state, get_backend, iter_frames

    backend = get_backend(backend_name)  # type: ignore[arg-type]
    try:
        backend.reset_state()
    except Exception:
        pass
    state = create_pipeline_state(cfg)  # type: ignore[arg-type]
    frame_ms: list[float] = []
    ops_ms: dict[str, list[float]] = {op: [] for op in OP_NAMES}
    scores_list: list[dict] = []
    cpu_before = time.process_time()
    wall_before = time.perf_counter()
    for idx, t_ms, frame in iter_frames(clip_path, cfg):  # type: ignore[arg-type]
        f0 = time.perf_counter()
        try:
            scores = analyze_frame(frame, state, cfg, backend, idx, t_ms)  # type: ignore[arg-type]
        except Exception as err:
            logger.warning("bench: frame %s failed (%s)", idx, type(err).__name__)
            continue
        frame_ms.append((time.perf_counter() - f0) * 1000.0)
        try:
            for op in OP_NAMES:
                ops_ms[op].append(float(scores.get("ops_ms", {}).get(op, 0.0)))
        except Exception:
            pass
        scores_list.append(scores)
    wall = time.perf_counter() - wall_before
    cpu = time.process_time() - cpu_before
    cpu_pct = round(100.0 * cpu / max(1e-9, wall), 1)
    return {"frame_ms": frame_ms, "ops_ms": ops_ms, "scores": scores_list, "cpu_pct": cpu_pct}


def _scores_equal(a: list[dict], b: list[dict]) -> tuple[bool, list[str]]:
    if len(a) != len(b):
        return False, [f"frame count {len(a)} != {len(b)}"]
    diffs: list[str] = []
    for x, y in zip(a, b):
        if x.get("frame_index") != y.get("frame_index"):
            return False, ["frame_index mismatch"]
        for k, xv in x.items():
            if k == "ops_ms":
                continue
            yv = y.get(k)
            try:
                if isinstance(xv, float) or isinstance(yv, float):
                    if round(float(xv), 3) != round(float(yv), 3):
                        diffs.append(f"{k}: {xv} != {yv} @frame {x.get('frame_index')}")
                elif xv != yv:
                    diffs.append(f"{k}: {xv} != {yv} @frame {x.get('frame_index')}")
            except Exception:
                diffs.append(f"{k}: uncomparable @frame {x.get('frame_index')}")
            if len(diffs) >= 3:
                return False, diffs
    return (len(diffs) == 0), diffs


def render_markdown(report: dict) -> str:
    """The human-readable twin of the JSON."""
    backends = report.get("backends", {})
    cool = backends.get("cool", {})
    base = backends.get("baseline", {})
    comp = report.get("comparison", {})
    host = report.get("host", {})
    versions = report.get("versions", {})
    params = report.get("params", {})
    L: list[str] = []
    L.append("# COOL vs baseline — Spaghetti Sentinel")
    L.append("")
    if report.get("authoritative") and comp.get("e2e_p95_speedup"):
        L.append(f"COOL is {comp['e2e_p95_speedup']}× faster at p95 on {host.get('label')}")
    else:
        reason = "; ".join(report.get("notes", [])[:2]) or "non-authoritative host"
        L.append(f"**NON-AUTHORITATIVE: {reason}**")
    L.append("")
    L.append("## How to reproduce")
    L.append("")
    L.append(f"Command: `{params.get('reproduce_command', 'python bench/run_bench.py')}`")
    L.append(f"Image digest: `{host.get('image_digest')}`")
    L.append(f"Instance type: `{host.get('instance_type')}`")
    clips = params.get("clips", [])
    L.append(f"Clips: `{', '.join(clips)}` with sha256s:")
    for c in params.get("clip_shas", []):
        L.append(f"- {c['id']}: `{c['sha256']}`")
    L.append(f"Repeats: {params.get('repeats')}, warmup: {params.get('warmup')}. "
             "Backends alternate per repeat so thermal drift hits both equally.")
    L.append("")
    L.append("## Host and versions")
    L.append("")
    L.append("| fact | value |")
    L.append("|---|---|")
    for k in ("label", "arch", "cpu_count", "instance_type", "ami_id", "image_digest", "region"):
        L.append(f"| {k} | {host.get(k)} |")
    for k in ("opencv", "cool", "python"):
        L.append(f"| {k} | {versions.get(k)} |")
    L.append("")
    L.append("## Headline")
    L.append("")
    L.append("| metric | baseline | cool | ratio |")
    L.append("|---|---|---|---|")
    L.append(f"| p50 ms | {base.get('e2e_ms', {}).get('p50')} | {cool.get('e2e_ms', {}).get('p50')} | "
             f"{comp.get('per_op_speedup', {}).get('_e2e_p50', '—')} |")
    L.append(f"| p95 ms | {base.get('e2e_ms', {}).get('p95')} | {cool.get('e2e_ms', {}).get('p95')} | "
             f"{comp.get('e2e_p95_speedup')} |")
    L.append(f"| fps | {base.get('fps')} | {cool.get('fps')} | {comp.get('fps_speedup')} |")
    L.append(f"| CPU % | {base.get('cpu_utilisation_pct')} | {cool.get('cpu_utilisation_pct')} | — |")
    L.append(f"| USD / 1000 frames | {base.get('usd_per_1000_frames')} | "
             f"{cool.get('usd_per_1000_frames')} | {comp.get('cost_reduction_pct')}% less |")
    L.append("")
    L.append("## Per-operation")
    L.append("")
    L.append("| op | baseline p50 | cool p50 | speedup | accelerated |")
    L.append("|---|---|---|---|---|")
    accel = set(cool.get("accelerated_ops", []))
    per_op = comp.get("per_op_speedup", {})
    for op in params.get("op_names", []):
        mark = "✓" if op in accel else ""
        L.append(f"| {op} | {base.get('per_op_ms', {}).get(op, {}).get('p50')} | "
                 f"{cool.get('per_op_ms', {}).get(op, {}).get('p50')} | "
                 f"{per_op.get(op)} | {mark} |")
    L.append("")
    L.append("## Does COOL execute the core workload?")
    L.append("")
    L.append(f"accelerated_ops: `{', '.join(cool.get('accelerated_ops', [])) or '(none)'}`")
    L.append(f"{comp.get('core_workload_share_pct')}% of per-frame pipeline time is spent "
             "inside COOL-accelerated operations.")
    L.append("")
    L.append("## Equivalence check")
    L.append("")
    L.append(f"scores_identical: {report.get('scores_identical')}")
    for d in report.get("score_diffs", [])[:3]:
        L.append(f"- {d}")
    if not report.get("scores_identical"):
        L.append("Backends produced different scores; speedups withheld — see notes.")
    L.append("")
    L.append("## Cost note")
    L.append("")
    rate = report.get("rate_used", 0.145)
    L.append(f"USD figures are MODELLED from the published us-east-1 on-demand rate of "
             f"${rate}/hour for {host.get('instance_type')}, not from a measured bill.")
    L.append("")
    L.append("## Notes")
    L.append("")
    for n in report.get("notes", []):
        L.append(f"- {n}")
    if not report.get("notes"):
        L.append("(none)")
    L.append("")
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="COOL vs baseline benchmark")
    ap.add_argument("--clips", default=None)
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--warmup", type=int, default=1)
    ap.add_argument("--backends", default="cool,baseline")
    ap.add_argument("--out", default="bench/results")
    ap.add_argument("--deployment-record", default="deploy/deployment-record.json")
    ap.add_argument("--label", default=None)
    ap.add_argument("--allow-non-graviton", action="store_true")
    args = ap.parse_args(argv)

    arch = platform.machine()
    if arch != "aarch64" and not args.allow_non_graviton:
        print(f"bench: host arch is {arch}, not aarch64 — the COOL award requires "
              "measurement on AWS Graviton")
        print("bench: re-run on the c7g instance, or pass --allow-non-graviton "
              "for a non-authoritative local run")
        return 2

    from app.config.settings import load_settings
    from app.vision import OP_NAMES, get_backend
    from app.vision.backend import cool_available, cool_version

    try:
        manifest = json.load(open("fixtures/manifest.json", encoding="utf-8"))
    except Exception as err:
        print(f"bench: cannot read fixtures/manifest.json ({err})")
        return 3
    wanted = args.clips.split(",") if args.clips else [c["id"] for c in manifest.get("clips", [])]
    clips = [c for c in manifest.get("clips", [])
             if c["id"] in wanted and c.get("ok") and os.path.exists(c["path"])]
    if not clips:
        print("bench: no readable clips")
        return 3

    cool_ok = cool_available()
    authoritative = (arch == "aarch64") and cool_ok
    notes: list[str] = []
    if arch != "aarch64":
        notes.append(f"non-Graviton host ({arch}); report is non-authoritative")
    if not cool_ok:
        notes.append("COOL build not present on this host; both columns are stock "
                     "OpenCV 5 and no COOL claim is supported")

    dep: dict = {}
    try:
        dep = json.load(open(args.deployment_record, encoding="utf-8"))
    except Exception:
        notes.append("deployment record not found; instance facts unavailable")

    backends = [b.strip() for b in args.backends.split(",") if b.strip()]
    try:
        thresholds = load_settings({}).thresholds
    except Exception:
        thresholds = {"warn": 0.45, "pause": 0.72, "confidence_floor": 0.55}

    # Warmup (discarded).
    for _ in range(max(0, args.warmup)):
        for b in backends:
            try:
                measure_pass(clips[0]["path"], b, {
                    "run_id": "warm", "source": clips[0]["path"], "backend": b,
                    "sample_every_n": 3, "max_frames": clips[0].get("frames", 300),
                    "roi": None, "thresholds": thresholds, "synthetic": True,
                    "replay": False, "evidence_prefix": "warm"})
            except Exception as err:
                logger.warning("bench: warmup failed (%s)", type(err).__name__)

    # Measured passes, alternating backend per repeat.
    agg: dict[str, dict] = {b: {"ms": [], "ops": {op: [] for op in OP_NAMES},
                                "cpu": [], "frames": 0} for b in backends}
    first_scores: dict[tuple[str, str], list[dict]] = {}
    for r in range(max(1, args.repeats)):
        for clip in clips:
            for b in backends:
                cfg = {"run_id": f"bench-{b}-{clip['id']}-{r}", "source": clip["path"],
                       "backend": b, "sample_every_n": 3,
                       "max_frames": clip.get("frames", 300), "roi": None,
                       "thresholds": thresholds, "synthetic": True, "replay": False,
                       "evidence_prefix": "bench"}
                res = measure_pass(clip["path"], b, cfg)
                agg[b]["ms"].extend(res["frame_ms"])
                for op in OP_NAMES:
                    agg[b]["ops"][op].extend(res["ops_ms"].get(op, []))
                agg[b]["cpu"].append(res["cpu_pct"])
                agg[b]["frames"] += len(res["frame_ms"])
                if r == 0:
                    first_scores[(clip["id"], b)] = res["scores"]

    import cv2

    instance_type = dep.get("instance_type") or ("c7g.xlarge" if arch == "aarch64" else None)
    rate = INSTANCE_HOURLY_USD.get(instance_type or "", 0.145)
    label = args.label or dep.get("url") or platform.platform()

    out_backends: dict[str, dict] = {}
    for b in backends:
        e2e = summarise(agg[b]["ms"])
        fps = round(len(agg[b]["ms"]) / (sum(agg[b]["ms"]) / 1000.0), 2) if agg[b]["ms"] else 0.0
        try:
            be = get_backend(b)  # type: ignore[arg-type]
            accel = list(getattr(be, "accelerated_ops", ()))
        except Exception:
            accel = []
        out_backends[b] = {
            "accelerated_ops": accel,
            "frames": agg[b]["frames"],
            "e2e_ms": e2e,
            "fps": fps,
            "cpu_utilisation_pct": round(sum(agg[b]["cpu"]) / max(1, len(agg[b]["cpu"])), 1),
            "per_op_ms": {op: summarise(agg[b]["ops"][op]) for op in OP_NAMES},
            "usd_per_1000_frames": usd_per_1000_frames(fps, rate),
        }
    if "cool" not in out_backends:
        out_backends["cool"] = {"accelerated_ops": [], "frames": 0,
                                "e2e_ms": summarise([]), "fps": 0.0,
                                "cpu_utilisation_pct": 0.0,
                                "per_op_ms": {op: summarise([]) for op in OP_NAMES},
                                "usd_per_1000_frames": 0.0}
    if "baseline" not in out_backends:
        out_backends["baseline"] = dict(out_backends["cool"])

    # Equivalence: compare first-repeat scores per clip across the two backends.
    scores_identical = True
    diffs: list[str] = []
    for clip in clips:
        a = first_scores.get((clip["id"], "cool"), [])
        c = first_scores.get((clip["id"], "baseline"), [])
        if a and c:
            same, d = _scores_equal(a, c)
            if not same:
                scores_identical = False
                diffs.extend(d)
    if "cool" not in backends or "baseline" not in backends:
        scores_identical = all(
            _scores_equal(first_scores.get((clip["id"], backends[0]), []),
                          first_scores.get((clip["id"], backends[0]), []))[0]
            for clip in clips)

    def ratio(a: float, b: float) -> float | None:
        try:
            if b <= 0:
                return None
            return round(a / b, 3)
        except Exception:
            return None

    cool_e2e = out_backends["cool"]["e2e_ms"]
    base_e2e = out_backends["baseline"]["e2e_ms"]
    cool_fps = out_backends["cool"]["fps"]
    base_fps = out_backends["baseline"]["fps"]
    cool_usd = out_backends["cool"]["usd_per_1000_frames"]
    base_usd = out_backends["baseline"]["usd_per_1000_frames"]
    per_op_speedup = {op: ratio(out_backends["baseline"]["per_op_ms"][op]["p50"],
                                max(1e-9, out_backends["cool"]["per_op_ms"][op]["p50"]))
                      if out_backends["cool"]["per_op_ms"][op]["p50"] > 0 else None
                      for op in OP_NAMES}
    try:
        cost_red = round(100.0 * (1 - cool_usd / max(1e-9, base_usd)), 1) if base_usd else 0.0
    except Exception:
        cost_red = 0.0
    accel_ops = out_backends["cool"]["accelerated_ops"]
    try:
        num = sum(out_backends["cool"]["per_op_ms"][op]["p50"] for op in accel_ops)
        den = sum(out_backends["cool"]["per_op_ms"][op]["p50"] for op in OP_NAMES)
        share = round(100.0 * num / max(1e-9, den), 1)
    except Exception:
        share = 0.0
    comparison = {
        "e2e_p95_speedup": ratio(base_e2e["p95"], max(1e-9, cool_e2e["p95"])),
        "fps_speedup": ratio(cool_fps, max(1e-9, base_fps)),
        "cost_reduction_pct": cost_red,
        "per_op_speedup": per_op_speedup,
        "cool_executed_core_workload": len(accel_ops) > 0,
        "core_workload_share_pct": share,
    }
    if not scores_identical:
        comparison["e2e_p95_speedup"] = None
        comparison["fps_speedup"] = None
        comparison["per_op_speedup"] = {op: None for op in OP_NAMES}
        notes.append("backends produced different scores; speedups withheld — see notes")

    total_frames = sum(agg[b]["frames"] for b in backends)
    report = {
        "schema": "cool-vs-baseline/1.0.0",
        "authoritative": bool(authoritative and cool_ok),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "host": {
            "label": label, "arch": arch, "cpu_count": os.cpu_count(),
            "instance_type": instance_type, "ami_id": dep.get("ami_id"),
            "image_digest": dep.get("image_digest"), "region": dep.get("region"),
        },
        "versions": {"opencv": cv2.__version__, "cool": cool_version(),
                     "python": platform.python_version()},
        "params": {"clips": [c["id"] for c in clips], "repeats": args.repeats,
                   "warmup": args.warmup, "work_resolution": "960x540",
                   "source_resolution": "1280x720", "sample_every_n": 3,
                   "frames_per_pass": clips[0].get("frames", 300) // 3 if clips else 0,
                   "op_names": list(OP_NAMES),
                   "clip_shas": [{"id": c["id"], "sha256": c.get("sha256", "")} for c in clips],
                   "reproduce_command": " ".join(sys.argv)},
        "backends": out_backends,
        "comparison": comparison,
        "scores_identical": scores_identical,
        "score_diffs": diffs[:10],
        "rate_used": rate,
        "notes": notes,
    }

    os.makedirs(args.out, exist_ok=True)
    jp = os.path.join(args.out, "cool-vs-baseline.json")
    mp = os.path.join(args.out, "cool-vs-baseline.md")
    with open(jp, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
        fh.write("\n")
    with open(mp, "w", encoding="utf-8") as fh:
        fh.write(render_markdown(report))
    print(f"bench: wrote {jp} and {mp}")
    if comparison.get("e2e_p95_speedup"):
        print(f"bench: p95 speedup {comparison['e2e_p95_speedup']}x "
              f"(baseline {base_e2e['p95']}ms vs cool {cool_e2e['p95']}ms)")
    else:
        print("bench: speedups withheld or unavailable — see report notes")
    print(f"bench: authoritative={report['authoritative']} frames={total_frames}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
