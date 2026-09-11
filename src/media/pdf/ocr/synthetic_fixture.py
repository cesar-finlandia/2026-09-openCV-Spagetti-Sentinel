# Requirement IDs: MED-04, MED-AC-01, GOV-REU-02, GOV-MIN-04, NONGOAL-06
"""Always-available offline OCR provider — DP-C §4.3 fixture note.

Paired automatically with the synthetic-fixture TEXT provider by the wrapper:
when the text layer is the checked-in fixture, the OCR fallback step "just
returns extract.json OCR text — no real OCR binary needed for offline CI".
Serves page 2's expected OCR text from extract.json. Fixture content is
Acme Corp/widget synthetic only (GOV-REU-02).
"""

from __future__ import annotations

import json
from pathlib import Path

from ..providers.types import OcrProvider, PdfOptions, register_ocr_provider

_cache: dict | None = None


def _load_extract() -> dict:
    global _cache
    if _cache is None:
        path = (
            Path(__file__).resolve().parents[4]
            / "examples"
            / "dummy-fixtures"
            / "media"
            / "pdf"
            / "extract.json"
        )
        _cache = json.loads(path.read_text(encoding="utf-8"))
    return _cache


class SyntheticFixtureOcrProvider:
    id = "synthetic-fixture"

    def available(self) -> bool:
        """Always available — pure offline fixture read, no binary required."""
        return True

    def ocr(self, page_image: bytes, opts: PdfOptions | None = None) -> dict:
        # Touch the fixture so a missing checked-in extract.json surfaces as a
        # provider error instead of silent canned output.
        _load_extract()
        # The scanned page in the fixture set is page 2; serve its expected
        # OCR text. Confidence is deliberately LOWER than the text layer's —
        # OCR pages reduce the weighted-mean confidence (§4.3 step 4).
        scanned = next((p for p in _cache["pages"] if p.get("ocr_used") is True), None)
        return {"text": scanned["text"] if scanned else "", "confidence": 0.8}


_INSTANCE = SyntheticFixtureOcrProvider()


def register() -> None:
    """Self-register so get_ocr_provider('synthetic-fixture') works."""
    register_ocr_provider(_INSTANCE)


synthetic_fixture_ocr_provider = _INSTANCE
