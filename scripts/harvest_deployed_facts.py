#!/usr/bin/env python3
"""Harvest the Fact Ledger and the architecture proof lines from the DEPLOYED instance.

DP-ARCHITECTURE WU-ARCH-02 and DP-SCRIPT WU-SC-01.

    python3 scripts/harvest_deployed_facts.py \
        --url http://ec2-35-94-80-183.us-west-2.compute.amazonaws.com \
        --project ../../hackathons/hackathon-projects/2026-09-openCV

It writes three things into <project>/:

    logs/deployed-probe.log     one self-describing fact per line - the proof source
    logs/deployed-facts.json    the same numbers, machine-readable
    architecture.json           patched in place with three harvested proof lines

and it refuses to write any of them unless TWO full sweeps agree on every number.
The policy is deterministic; a disagreement is a defect, not something to average.

Standard library only, so it runs wherever the operator's shell runs. It polls
GET /events?trace_id=... (the snapshot shape) rather than the SSE stream, because
a poll is restartable and an SSE reconnect in the middle of a sweep would lose
decisions and silently change a number that ends up spoken in a video.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

FIXTURES = ["good-first-layer", "stringing", "spaghetti", "lighting-shift"]
TIMEOUT = 30


class Fail(Exception):
    pass


def get(url: str, path: str) -> dict:
    try:
        with urllib.request.urlopen(url.rstrip("/") + path, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise Fail(f"GET {path} -> HTTP {e.code}") from e
    except Exception as e:
        raise Fail(f"GET {path} -> {type(e).__name__}: {e}") from e


def post(url: str, path: str, body: dict) -> tuple[int, dict]:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url.rstrip("/") + path, data=data,
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8"))
        except Exception:
            return e.code, {}
    except Exception as e:
        raise Fail(f"POST {path} -> {type(e).__name__}: {e}") from e


def clear_stuck_run(url: str) -> str | None:
    """A run left open answers 409 to every new run - including a judge's.

    Returns a note for the log, or None when nothing was stuck.
    """
    status, body = post(url, "/api/runs", {"fixture_id": FIXTURES[0]})
    if status == 200:
        # nothing was stuck; drain the probe run we just started
        drain(url, body["run_id"])
        return None
    if status != 409:
        raise Fail(f"POST /api/runs answered {status}: {body}")
    run_id = body.get("run_id")
    if not run_id:
        raise Fail("409 with no run_id - cannot clear the stuck run")
    # answer any approval it is waiting on, then let it finish
    for _ in range(40):
        snap = get(url, f"/events?trace_id={run_id}")
        for ap in pending_approvals(snap.get("events", [])):
            post(url, f"/api/runs/{run_id}/approve",
                 {"approval_id": ap, "approved": True})
        rec = get(url, f"/api/runs/{run_id}")
        if rec.get("status") not in ("running", "pending", "awaiting_approval"):
            return f"cleared a stuck run {run_id} (status {rec.get('status')})"
        time.sleep(3)
    raise Fail(f"run {run_id} would not clear - stop and clear it by hand before the take")


def pending_approvals(events: list) -> list[str]:
    """Every approval still waiting for a human, oldest first.

    The deployed API nests the id: step_id == "await-approval" carries
    {"approval_id", "decision"}, and step_id == "approval-resolved" marks
    it answered (web/scripts/screenshots.mjs autoApprover reads the same
    shape). The legacy flat shape (step == "approval" with top-level
    approval_id / requires_human) is kept so mock proofs still pass.
    """
    resolved = {
        (e.get("payload") or {}).get("approval_id")
        for e in events if e.get("step_id") == "approval-resolved"
    }
    out: list[str] = []
    for e in events:
        p = e.get("payload") or {}
        aid = p.get("approval_id")
        if e.get("step_id") == "await-approval" and aid and aid not in resolved:
            if str(aid) not in out:
                out.append(str(aid))
            continue
        if e.get("step") == "approval" and aid and not p.get("resolved"):
            if str(aid) not in out:
                out.append(str(aid))
        elif p.get("requires_human") and aid:
            if str(aid) not in out:
                out.append(str(aid))
    return out


def pending_approval(events: list) -> str | None:
    all_pending = pending_approvals(events)
    return all_pending[0] if all_pending else None


def drain(url: str, run_id: str, auto_approve: bool = True) -> list:
    """Poll to terminal state, approving whatever is asked. Returns the events."""
    events: list = []
    # A spaghetti run asks ~37 approvals; at ~2-4 s per poll cycle with
    # instant approval the run still needs several minutes of frame
    # processing, so the budget is generous. This is client patience, not
    # a product claim.
    for _ in range(400):
        snap = get(url, f"/events?trace_id={run_id}")
        events = snap.get("events", []) or events
        if auto_approve:
            for ap in pending_approvals(events):
                post(url, f"/api/runs/{run_id}/approve", {"approval_id": ap, "approved": True})
        rec = get(url, f"/api/runs/{run_id}")
        if rec.get("status") not in ("running", "pending", "awaiting_approval"):
            snap = get(url, f"/events?trace_id={run_id}")
            return snap.get("events", []) or events
        time.sleep(2)
    raise Fail(f"run {run_id} never reached a terminal state")


def decisions_of(events: list) -> list:
    out = []
    for e in events:
        p = e.get("payload") or {}
        # deployed shape nests the decision (decide -> {"decision": {...}});
        # the flat shape is kept so mock proofs still pass.
        d = p.get("decision") if isinstance(p.get("decision"), dict) else p
        if "action" in d and "spaghetti_score" in d:
            out.append(d)
    return out


def scores_of(events: list) -> list:
    out = []
    for e in events:
        p = e.get("payload") or {}
        # deployed shape nests the scores (perceive -> {"scores": {...}}).
        s = p.get("scores") if isinstance(p.get("scores"), dict) else p
        if "spaghetti_score" in s and "frame_index" in s:
            out.append(s)
    return out


def _evidence_uris(events: list) -> set[str]:
    """Distinct evidence clips referenced by a run.

    Deployed shape: evidence-stored carries {"uri": ...} and decide
    carries {"decision": {"evidence_uri": ...}}; the flat
    payload.evidence_uri shape is kept so mock proofs still pass.
    """
    uris: set[str] = set()
    for e in events:
        p = e.get("payload") or {}
        if p.get("uri") and e.get("step_id") == "evidence-stored":
            uris.add(str(p["uri"]))
        if p.get("evidence_uri"):
            uris.add(str(p["evidence_uri"]))
        d = p.get("decision")
        if isinstance(d, dict) and d.get("evidence_uri"):
            uris.add(str(d["evidence_uri"]))
    return uris


def sweep(url: str) -> dict:
    facts: dict = {}
    for fid in FIXTURES:
        status, body = post(url, "/api/runs", {"fixture_id": fid})
        # the body field is fixture_id, never "fixture": a wrong field silently
        # runs the first clip and there is no pause to film.
        if status == 409:
            raise Fail("a run is already active - clear it first")
        if status != 200:
            raise Fail(f"POST /api/runs {fid} -> {status}: {body}")
        run_id = body["run_id"]
        t0 = time.time()
        events = drain(url, run_id)
        wall = round(time.time() - t0, 1)

        dec = decisions_of(events)
        sc = scores_of(events)
        alerts = [d for d in dec if d.get("action") != "continue"]
        pause = next((d for d in dec if d.get("action") == "request_pause_approval"), None)
        facts[fid] = {
            "run_id": run_id,
            "frames_sampled": len(sc),
            "decisions": len(dec),
            "peak_spaghetti_score": round(max((s["spaghetti_score"] for s in sc), default=0.0), 4),
            "escalations": len(alerts),
            "first_alert": (
                {"frame_index": alerts[0]["frame_index"], "t_ms": alerts[0].get("t_ms"),
                 "action": alerts[0]["action"],
                 "spaghetti_score": round(alerts[0]["spaghetti_score"], 4),
                 "threshold": alerts[0].get("threshold"),
                 "reason_code": alerts[0].get("reason_code")}
                if alerts else None),
            "pause_recommended": pause is not None,
            "pause": (
                {k: (round(pause[k], 4) if isinstance(pause.get(k), float) else pause.get(k))
                 for k in ("frame_index", "t_ms", "spaghetti_score", "confidence",
                           "threshold", "reason_code", "requires_human", "rationale_source")}
                if pause else None),
            "evidence_clips": len(_evidence_uris(events)),
            "wall_clock_s": wall,
        }
    return facts


VOLATILE = {"run_id", "wall_clock_s"}


def disagreements(a: dict, b: dict, path: str = "") -> list[str]:
    out: list[str] = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k in VOLATILE:
                continue
            out += disagreements(a.get(k), b.get(k), f"{path}.{k}" if path else k)
    elif a != b:
        out.append(f"{path}: {a!r} vs {b!r}")
    return out


def write_log(project: str, health: dict, fixtures: list, facts: dict,
              notes: list[str]) -> tuple[str, list[str]]:
    lines: list[str] = []
    lines.append(f"harvested {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} "
                 f"from {health['_url']}")
    lines.append(f"health status={health.get('status')} uptime_s={health.get('uptime_s')} "
                 f"build_marker={health.get('build_marker')}")
    lines.append(f"runtime opencv={health.get('opencv_version')} "
                 f"cool_version={health.get('cool_version')} "
                 f"backend_requested={health.get('backend')} arch={health.get('arch')} "
                 f"python={health.get('python')}")
    lines.append(f"evidence backend={(health.get('evidence') or {}).get('backend')} "
                 f"bucket={(health.get('evidence') or {}).get('bucket')} "
                 f"writable={(health.get('evidence') or {}).get('writable')}")
    lines.append("fixtures " + " ".join(fixtures))
    for fid in FIXTURES:
        f = facts[fid]
        lines.append(f"run {fid} frames_sampled={f['frames_sampled']} "
                     f"decisions={f['decisions']} peak={f['peak_spaghetti_score']} "
                     f"escalations={f['escalations']} pause={f['pause_recommended']} "
                     f"evidence_clips={f['evidence_clips']}")
        fa = f["first_alert"]
        if fa:
            lines.append(f"alert {fid} frame={fa['frame_index']} t_ms={fa['t_ms']} "
                         f"action={fa['action']} score={fa['spaghetti_score']} "
                         f"threshold={fa['threshold']} reason={fa['reason_code']}")
        else:
            lines.append(f"alert {fid} none - no escalation at any frame")
        p = f["pause"]
        if p:
            lines.append(f"pause {fid} frame={p['frame_index']} t_ms={p['t_ms']} "
                         f"score={p['spaghetti_score']} confidence={p['confidence']} "
                         f"threshold={p['threshold']} reason={p['reason_code']} "
                         f"requires_human={p['requires_human']}")
    for n in notes:
        lines.append(f"note {n}")
    lines.append("both sweeps agreed on every recorded number")
    path = os.path.join(project, "logs", "deployed-probe.log")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return path, lines



def patch_architecture(project: str, lines: list[str]) -> list[str]:
    """Write the three proof lines into architecture.json, by line number.

    Never type a proof by hand: lint-architecture.ts opens the file at the line
    and fails if the text does not match, and that check is the whole point.
    """
    def find(prefix: str) -> tuple[int, str]:
        for i, ln in enumerate(lines, start=1):
            if ln.startswith(prefix):
                return i, ln
        raise Fail(f"no harvested line starts with {prefix!r}")

    proofs = {
        "backend-ec2": find("runtime "),
        "ops-agent": find("run spaghetti "),
        "policy-human": find("pause spaghetti "),
    }
    ap = os.path.join(project, "architecture.json")
    with open(ap, encoding="utf-8") as fh:
        arch = json.load(fh)
    for e in arch["edges"]:
        hit = proofs.get(e.get("id"))
        if hit:
            e["proof"] = {"file": "logs/deployed-probe.log", "line": hit[0], "text": hit[1]}
    with open(ap, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(arch, indent=2) + "\n")
    return [f"{k} -> line {v[0]}" for k, v in proofs.items()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True, help="the DEPLOYED base URL, never localhost")
    ap.add_argument("--project", required=True,
                    help="hackathon-projects/2026-09-openCV - where the artefacts are written")
    ap.add_argument("--sweeps", type=int, default=2)
    args = ap.parse_args()

    if "localhost" in args.url or "127.0.0.1" in args.url:
        print("refusing: the ledger must be measured against the DEPLOYED instance "
              "(demo-video-script.spec.md §5). A local number and a recorded frame "
              "that disagree is the defect this script exists to prevent.", file=sys.stderr)
        return 2

    notes: list[str] = []
    try:
        health = get(args.url, "/healthz")
        health["_url"] = args.url
        if health.get("status") not in ("ok", "degraded"):
            raise Fail(f"/healthz says {health.get('status')}")
        fixtures = [c["id"] for c in (get(args.url, "/api/fixtures").get("clips") or [])]
        missing = [f for f in FIXTURES if f not in fixtures]
        if missing:
            raise Fail(f"the deployed instance is missing fixtures: {missing}")

        note = clear_stuck_run(args.url)
        if note:
            notes.append(note)

        sweeps = []
        for n in range(args.sweeps):
            print(f"sweep {n + 1} of {args.sweeps} ...", file=sys.stderr)
            sweeps.append(sweep(args.url))
        for i in range(1, len(sweeps)):
            diff = disagreements(sweeps[0], sweeps[i])
            if diff:
                print("the sweeps disagree - the policy is deterministic, so this is a "
                      "defect, not noise. Fix it before writing a script:", file=sys.stderr)
                for d in diff:
                    print("  " + d, file=sys.stderr)
                return 3

        facts = sweeps[0]
        path, lines = write_log(args.project, health, fixtures, facts, notes)
        jpath = os.path.join(args.project, "logs", "deployed-facts.json")
        with open(jpath, "w", encoding="utf-8") as fh:
            json.dump({"url": args.url, "harvested_at": time.time(),
                       "health": {k: v for k, v in health.items() if k != "_url"},
                       "fixtures": fixtures, "runs": facts, "notes": notes,
                       "sweeps_agreed": True}, fh, indent=2)
        placed = patch_architecture(args.project, lines)
        print(f"wrote {path}")
        print(f"wrote {jpath}")
        print("patched architecture.json proofs: " + ", ".join(placed))
        print("now run: node ../../hackathons/scripts/lint-architecture.ts " + args.project)
        return 0
    except Fail as e:
        print(f"harvest failed: {e}", file=sys.stderr)
        print("Nothing was written. Do not substitute a local measurement for a deployed one.",
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
