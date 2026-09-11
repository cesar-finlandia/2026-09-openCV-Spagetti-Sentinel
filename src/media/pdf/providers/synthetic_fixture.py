# Requirement IDs: MED-04, MED-AC-01, GOV-REU-02, GOV-MIN-04, NONGOAL-06
"""Always-available offline PDF text provider — DP-C §4.3 built-in.

Reads the checked-in synthetic fixture pair:
  examples/dummy-fixtures/media/pdf/sample.pdf   (born-digital p1, scanned p2)
  examples/dummy-fixtures/media/pdf/extract.json (expected extraction)

Per §4.3 fixture note: returns REAL text for born-digital p1 and DELIBERATELY
SHORT text for scanned p2 so the wrapper's per-page ocrThresholdChars check
trips and the OCR fallback step runs. The paired OCR step in synthetic-fixture
mode is served by pdf/ocr/synthetic_fixture.py straight from extract.json —
NO real OCR binary needed for offline CI (GOV-MIN-04 / MED-AC-01).
"""

from __future__ import annotations

import json
from pathlib import Path

from .types import PdfParseError, PdfTextProvider, register_pdf_text_provider

#: Marker emitted for image-only pages — intentionally < ocrThresholdChars
#: (default 40) so the wrapper's OCR fallback triggers (§4.3 step 2).
SCANNED_PAGE_MARKER = "[scanned page]"

_REPO_ROOT = Path(__file__).resolve().parents[4]

_cache: dict | None = None


def _repo_root() -> Path:
    # src/media/pdf/providers/synthetic_fixture.py → repo root is parents[4]
    return Path(__file__).resolve().parents[4]


def _load_extract() -> dict:
    global _cache
    if _cache is None:
        path = _repo_root() / "examples" / "dummy-fixtures" / "media" / "pdf" / "extract.json"
        _cache = json.loads(path.read_text(encoding="utf-8"))
    return _cache


def _assert_fixture_pdf(pdf: PdfInput) -> None:
    if not isinstance(pdf, dict) or "path" not in pdf:
        return
    data = Path(pdf["path"]).read_bytes()
    if data[:5] != b"%PDF-":
        raise PdfParseError(f'fixture {pdf["path"]} is not a PDF (%PDF header missing)')


class SyntheticFixturePdfTextProvider:
    id = "synthetic-fixture"

    def extract_text(self, pdf: PdfInput) -> dict:
        _assert_fixture_pdf(pdf)
        fixture = _load_extract()
        text_by_page = [
            {
                "page": p["page"],
                # Born-digital page → full expected text; scanned page → short
                # marker that forces the §4.3 OCR branch.
                "text": SCANNED_PAGE_MARKER if p.get("ocr_used") else p["text"],
            }
            for p in fixture["pages"]
        ]
        return {"text_by_page": text_by_page, "confidence": 0.95}


_INSTANCE = SyntheticFixturePdfTextProvider()


def register() -> None:
    """Self-register so get_pdf_text_provider('synthetic-fixture') works."""
    register_pdf_text_provider(_INSTANCE)


synthetic_fixture_pdf_text_provider = _INSTANCE
