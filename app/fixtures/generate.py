"""Synthetic fixture generator — REQ-F14 / REQ-N08.

Every clip is drawn procedurally from a fixed seed, so the same command on any machine
produces byte-identical frames. Every frame carries a visible "SYNTHETIC" watermark, and
fixtures/manifest.json carries "synthetic": true at the top level.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
from datetime import datetime, timezone
from typing import TypedDict

logger = logging.getLogger("fixtures.generate")

FIXTURE_IDS: tuple[str, ...] = ("good-first-layer", "stringing", "spaghetti", "lighting-shift")
"""The four labelled scenarios. Adding a fifth means editing this tuple AND labels.json."""

CLIP_WIDTH: int = 1280
CLIP_HEIGHT: int = 720
CLIP_FPS: float = 30.0
CLIP_FRAMES: int = 300
"""720p / 30 fps / 10 s per clip — the resolution the COOL claim is measured at."""

WATERMARK_TEXT: str = "SYNTHETIC — generated demo footage"


class FixtureSpec(TypedDict):
    id: str
    label: str          # "nominal" | "warning" | "failure"
    onset_frame: int | None   # first frame where the defect is visible; None for nominal
    seed: int
    notes: str


FIXTURE_SPECS: tuple[FixtureSpec, ...] = (
    {"id": "good-first-layer", "label": "nominal", "onset_frame": None, "seed": 101,
     "notes": "Steady, regular infill. The agent must never request a pause on this clip."},
    {"id": "stringing", "label": "warning", "onset_frame": 120, "seed": 202,
     "notes": "Thin wisps appear from frame 120. Expect capture_evidence, not a pause."},
    {"id": "spaghetti", "label": "failure", "onset_frame": 150, "seed": 303,
     "notes": "Extruded filament detaches from frame 150 and accumulates. Expect a pause request."},
    {"id": "lighting-shift", "label": "nominal", "onset_frame": None, "seed": 404,
     "notes": "Global brightness ramps ±35% with the print unchanged. A false positive here is a defect."},
)


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def render_clip(spec: FixtureSpec, path: str) -> dict:
    """Render one clip to `path`. Returns {id, path, frames, fps, width, height, sha256, ok}."""
    import cv2
    import numpy as np

    try:
        rng = np.random.default_rng(spec["seed"])
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), CLIP_FPS, (CLIP_WIDTH, CLIP_HEIGHT))
        # Static base.
        base = np.full((CLIP_HEIGHT, CLIP_WIDTH, 3), (38, 38, 40), dtype=np.uint8)
        cv2.rectangle(base, (160, 90), (1120, 630), (62, 62, 66), -1)
        cv2.rectangle(base, (160, 90), (1120, 630), (90, 90, 96), 3)
        for i in range(CLIP_FRAMES):
            frame = base.copy()
            rows = min(26, 4 + i // 11)
            y0 = 110
            for r in range(rows):
                y = y0 + r * 20
                if y > 610:
                    break
                jitter = int(rng.normal(0, 0.6))
                x1 = 180 + jitter
                x2 = 1100 + jitter
                # Spaghetti blanks out infill rows (the overlay below repaints
                # them dark; skip drawing them here too).
                if spec["id"] == "spaghetti" and i >= 150:
                    kill = min(22, (i - 150) // 3)
                    if r >= 26 - kill - 1:
                        continue
                cv2.line(frame, (x1, y), (x2, y), (178, 150, 96), 6)
            fid = spec["id"]
            if fid == "stringing" and i >= 120:
                n = min(40, (i - 120) // 3)
                for _ in range(n):
                    px = int(rng.integers(180, 1100))
                    py = int(rng.integers(110, 610))
                    ang = float(rng.uniform(0, 2 * math.pi))
                    ln = int(rng.integers(8, 26))
                    ex = int(px + ln * math.cos(ang))
                    ey = int(py + ln * math.sin(ang))
                    cv2.line(frame, (px, py), (ex, ey), (198, 178, 130), 1)
            elif fid == "spaghetti" and i >= 150:
                # Dark gouges: paint bed-dark rectangles over infill rows so
                # first_layer_coverage collapses (drives the coverage term).
                kill_rows = min(22, (i - 150) // 3)
                for kr in range(kill_rows):
                    yk = 110 + (26 - kr - 1) * 20
                    if 100 <= yk <= 615:
                        cv2.rectangle(frame, (175, yk - 9), (1105, yk + 9), (38, 38, 40), -1)
                n = min(220, 4 * (i - 150))
                for _ in range(n):
                    px = int(rng.integers(180, 1100))
                    py = int(rng.integers(110, 610))
                    pts = [(px, py)]
                    cx, cy = px, py
                    for _k in range(5):
                        cx += int(rng.integers(-30, 31))
                        cy += int(rng.integers(-30, 31))
                        pts.append((cx, cy))
                    arr = np.array(pts, dtype=np.int32).reshape((-1, 1, 2))
                    cv2.polylines(frame, [arr], False, (215, 196, 150), 4)
                # Extra bright blobs that appear/disappear frame to frame,
                # driving motion_energy and texture_disorder hard.
                nb = min(60, (i - 150))
                for _ in range(nb):
                    bx = int(rng.integers(180, 1080))
                    by = int(rng.integers(110, 590))
                    cv2.circle(frame, (bx, by), int(rng.integers(6, 24)), (225, 205, 160), -1)
            elif fid == "lighting-shift":
                factor = 1.0 + 0.35 * math.sin(2 * math.pi * i / 150.0)
                frame = np.clip(frame.astype(np.float32) * factor, 0, 255).astype(np.uint8)
            noise = rng.normal(0, 2.0, frame.shape)
            frame = np.clip(frame.astype(np.float32) + noise, 0, 255).astype(np.uint8)
            cv2.putText(frame, WATERMARK_TEXT, (24, CLIP_HEIGHT - 24),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 230, 230), 2, cv2.LINE_AA)
            writer.write(frame)
        writer.release()
        digest = _sha256_file(path)
        return {"id": spec["id"], "path": path, "frames": CLIP_FRAMES, "fps": CLIP_FPS,
                "width": CLIP_WIDTH, "height": CLIP_HEIGHT, "sha256": digest, "ok": True}
    except Exception as err:
        logger.error("fixtures: render %s failed (%s)", spec["id"], type(err).__name__)
        return {"id": spec["id"], "path": path, "frames": CLIP_FRAMES, "fps": CLIP_FPS,
                "width": CLIP_WIDTH, "height": CLIP_HEIGHT, "sha256": "", "ok": False}


def generate_fixtures(out_dir: str = "fixtures", ids: tuple[str, ...] = FIXTURE_IDS) -> dict:
    """Render every requested clip into <out_dir>/clips/<id>.mp4 and write the manifest."""
    os.makedirs(os.path.join(out_dir, "clips"), exist_ok=True)
    by_id = {s["id"]: s for s in FIXTURE_SPECS}
    clips = []
    for fid in FIXTURE_IDS:
        if fid not in ids:
            continue
        spec = by_id[fid]
        rel = os.path.join(out_dir, "clips", f"{fid}.mp4").replace("\\", "/")
        res = render_clip(spec, rel)
        clips.append({
            "id": fid, "path": rel, "label": spec["label"],
            "onset_frame": spec["onset_frame"], "frames": res.get("frames", CLIP_FRAMES),
            "seed": spec["seed"], "sha256": res.get("sha256", ""),
            "notes": spec["notes"], "ok": bool(res.get("ok")),
        })
    manifest = {
        "synthetic": True,
        "generator": "app/fixtures/generate.py",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "width": CLIP_WIDTH, "height": CLIP_HEIGHT, "fps": CLIP_FPS,
        "watermark": WATERMARK_TEXT,
        "clips": clips,
    }
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=False)
        fh.write("\n")
    labels = {
        "synthetic": True,
        "labels": {c["id"]: {"label": c["label"], "onset_frame": c["onset_frame"]} for c in clips},
    }
    with open(os.path.join(out_dir, "labels.json"), "w", encoding="utf-8") as fh:
        json.dump(labels, fh, indent=2, sort_keys=False)
        fh.write("\n")
    return manifest
