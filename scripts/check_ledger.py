#!/usr/bin/env python3
"""Fail until the spoken numbers match the numbers harvested from the DEPLOYED build.

DP-SCRIPT §4. `demo-video-script.md` is written with a PROVISIONAL ledger, because the
script has to exist before the deployed box can be measured. This script is what turns
that word into something enforceable: it re-derives every claim the narration makes from
`logs/deployed-facts.json` and refuses the script while any one of them disagrees.

    python3 scripts/check_ledger.py ../../hackathons/hackathon-projects/2026-09-openCV

Exit 0 only when every claim below is backed by the harvest.
"""
from __future__ import annotations

import json
import os
import sys

def spoken(segments: list, phrase: str) -> bool:
    return any(phrase in s["text"] for s in segments)


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    project = sys.argv[1]
    fpath = os.path.join(project, "logs", "deployed-facts.json")
    if not os.path.exists(fpath):
        print(f"no harvest at {fpath}\n"
              "Run scripts/harvest_deployed_facts.py against the DEPLOYED url first. "
              "A ledger measured anywhere else is the defect this check exists to catch.",
              file=sys.stderr)
        return 1
    facts = json.load(open(fpath, encoding="utf-8"))
    if not facts.get("sweeps_agreed"):
        print("the harvest did not record two agreeing sweeps", file=sys.stderr)
        return 1

    segs = json.load(open(os.path.join(project, "narration-segments.json"),
                          encoding="utf-8"))["segments"]
    beat = json.load(open(os.path.join(project, "beat-plan.json"), encoding="utf-8"))

    problems: list[str] = []

    sp = facts["runs"]["spaghetti"]
    li = facts["runs"]["lighting-shift"]
    st = facts["runs"]["stringing"]
    pause = sp["pause"] or {}

    if not sp["pause_recommended"]:
        problems.append("the spaghetti fixture no longer reaches a pause request - "
                        "the whole demo beat is built on it")
    if li["pause_recommended"]:
        problems.append("the lighting-shift fixture now escalates to a pause - s7 and s9 both "
                        "say it does not, and that claim is now false")
    if not st["escalations"]:
        problems.append("the stringing fixture no longer nudges - s9 says it does")

    def want(label: str, value, phrase: str) -> None:
        if value is None:
            problems.append(f"{label}: the harvest has no value for it")
        elif not spoken(segs, phrase):
            problems.append(f"{label}: no segment says {phrase!r}")

    # the spoken forms, checked against the harvested values
    if pause.get("frame_index") != 195:
        problems.append(f"pause frame is now {pause.get('frame_index')}, the script says 195 "
                        "(s5: 'frame one hundred and ninety five')")
    want("pause frame", pause.get("frame_index"), "frame one hundred and ninety five")

    if pause.get("threshold") not in (0.72,):
        problems.append(f"pause threshold is now {pause.get('threshold')}, the script says 0.72")
    want("pause threshold", pause.get("threshold"), "zero point seven two")

    t = pause.get("t_ms")
    if t is None or abs(t - 6500) > 250:
        problems.append(f"the pause is now at {t} ms; the script says six and a half seconds")

    c = pause.get("confidence")
    if c is None or abs(round(c, 2) - 0.77) > 0.005:
        problems.append(f"confidence at the pause is now {c}; the script says 0.77")

    p = li["peak_spaghetti_score"]
    if p is None or abs(round(p, 2) - 0.27) > 0.005:
        problems.append(f"lighting-shift peak is now {p}; s7 says zero point two seven")

    # the B1 stat and the B5b table are on screen, so they are checked too
    stat = beat["beats"][0]["props"]["stat"]["value"]
    if abs(stat - round(sp["peak_spaghetti_score"], 2)) > 0.005:
        problems.append(f"beat-plan B1 stat is {stat}; the harvested peak is "
                        f"{sp['peak_spaghetti_score']}")
    table = " ".join(beat["beats"][6]["props"]["lines"])
    for fid in ("good-first-layer", "stringing", "spaghetti", "lighting-shift"):
        peak = round(facts["runs"][fid]["peak_spaghetti_score"], 2)
        if f"{peak:.2f}" not in table:
            problems.append(f"B5b's table does not carry {fid}'s harvested peak {peak:.2f}")

    if problems:
        print("the ledger and the harvest disagree - the harvest is right:", file=sys.stderr)
        for p2 in problems:
            print("  - " + p2, file=sys.stderr)
        print("\nFix demo-video-script.md §5, narration-segments.json and beat-plan.json, then "
              "re-run. Do not record until this is clean.", file=sys.stderr)
        return 1

    print("ledger OK - every spoken number is backed by the deployed harvest")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
