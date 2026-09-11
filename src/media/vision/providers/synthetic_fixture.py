# Requirement IDs: MED-04, MED-AC-01, MED-REU-01, GOV-REU-02, GOV-MIN-04, NONGOAL-06
"""Always-available offline vision provider — Python mirror of
synthetic-fixture.ts (DP-C §4.2).

Reads the checked-in synthetic fixture pair:
    examples/dummy-fixtures/media/vision/sample.png    (640x480 synthetic scene)
    examples/dummy-fixtures/media/vision/caption.json  (expected output)
and returns caption.json verbatim — NO network, NO credentials. This is what
MED-AC-01 offline tests rely on. Fixture content is Acme Corp/widget synthetic
only (GOV-REU-02); the `synthetic` provenance flag is set by the wrapper
because this provider's id is "synthetic-fixture" (MED-04).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from .types import ImageInput, VisionOptions, VisionProvider, VisionResult

_REPO_ROOT = Path(__file__).resolve().parents[4]
CAPTION_PATH = _REPO_ROOT / "examples" / "dummy-fixtures" / "media" / "vision" / "caption.json"

_cache: Dict[str, Any] | None = None


def _load_caption() -> Dict[str, Any]:
    global _cache
    if _cache is None:
        _cache = json.loads(CAPTION_PATH.read_text(encoding="utf-8"))
    return _cache


def _fixture_bytes(input: ImageInput) -> bytes | None:
    """Return raw bytes when the input references a checked-in image file by
    path, so a corrupt/missing fixture surfaces as an error instead of
    silently returning canned text. None = nothing to sniff."""
    if isinstance(input, dict) and isinstance(input.get("path"), str):
        return Path(str(input["path"])).read_bytes()
    return None


def _assert_image(data: bytes) -> None:
    png_magic = b"\x89PNG\r\n\x1a\n"
    jpeg_magic = b"\xff\xd8\xff"
    if not (data[:8] == png_magic or data[:3] == jpeg_magic):
        raise ValueError("fixture image is not a PNG/JPEG file")


class SyntheticFixtureVisionProvider:
    id = "synthetic-fixture"

    def caption(self, input: ImageInput, opts: VisionOptions | None = None) -> VisionResult:
        img = _fixture_bytes(input)
        if img is not None:
            _assert_image(img)
        c = _load_caption()
        return VisionResult(
            text=str(c.get("text", "")),
            confidence=0.92,
            structured={
                "objects": c.get("objects", []) if isinstance(c.get("objects"), list) else [],
                "dimensions": {"width": 640, "height": 480},
                "model": "synthetic-fixture",
            },
        )


_INSTANCE = SyntheticFixtureVisionProvider()


def register() -> None:
    from .types import register_vision_provider

    register_vision_provider(_INSTANCE)
