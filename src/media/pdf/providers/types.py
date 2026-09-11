# Requirement IDs: MED-01, MED-03, MED-REU-02, RES-03, GOV-MIN-04, XCUT-08
"""PDF provider abstraction + runtime registries (Python) — DP-C §4.3.

Two layered providers, configured independently but invoked by ONE wrapper;
the OCR fallback lives INSIDE the wrapper (mechanical), not via RES-03:

  - PdfTextProvider — text-layer extraction ("pypdf" | "synthetic-fixture" | "none")
  - OcrProvider     — page-image OCR ("tesseract" | "synthetic-fixture" | "none")

Providers register via register_pdf_text_provider()/register_ocr_provider();
the wrapper resolves at CALL time so MED_PDF_PROVIDER / MED_OCR_PROVIDER env
swaps need zero code change (MED-03). A missing text-provider id returns
None → wrapper raises MediaError("unknown_provider") per DP-C §7.2.

Isolation (MED-REU-02): imports nothing outside src/media shared surfaces —
never stt/vision/tts.
"""

from __future__ import annotations

from typing import Any, Protocol

__all__ = [
    "PdfInput",
    "PdfOptions",
    "PdfPageText",
    "PdfTextResult",
    "PdfTextProvider",
    "OcrResult",
    "OcrProvider",
    "PdfParseError",
    "register_pdf_text_provider",
    "get_pdf_text_provider",
    "list_pdf_text_providers",
    "register_ocr_provider",
    "get_ocr_provider",
    "list_ocr_providers",
]

#: Raw document input variants accepted by extract() — PDF ONLY (other docs →
#: ``unsupported_format``; scope is PDF per requirement).
PdfInput = dict  # {"path": str} | {"buffer": bytes} | {"base64": str}

#: Per-wrapper options: MediaConfig slice + generic hints only (MED-REU-01).
PdfOptions = dict  # ocrThresholdChars/ocr_threshold_chars, ocr_languages, ...


class PdfPageText(Protocol):
    """One extracted page: {page:int, text:str}."""


class PdfTextResult(Protocol):
    """Normalized text-provider result: textByPage/text_by_page + confidence."""


class PdfTextProvider(Protocol):
    """One PDF text-layer backend.

    Implementations MUST raise on failure so RES-01 can retry/fallback;
    parse-shaped failures MUST raise PdfParseError so the wrapper maps them
    to error:"corrupt_file" per the §4.3 failure table.
    """

    id: str

    def extract_text(self, pdf: PdfInput) -> dict[str, Any]:
        """Return {'text_by_page': [{'page', 'text'}...], 'confidence': float}."""
        ...


class OcrResult(Protocol):
    """Normalized OCR result for one rendered page image."""


class OcrProvider(Protocol):
    """One OCR engine backend (§4.3 second layer).

    ``available()`` is checked by the wrapper BEFORE invoking ocr(); when a
    binary-backed engine is missing the wrapper degrades gracefully
    (GOV-RES-04) — no throw.
    """

    id: str

    def available(self) -> bool: ...

    def ocr(self, page_image: bytes, opts: PdfOptions | None = None) -> dict[str, Any]:
        """Return {'text': str, 'confidence': float}."""
        ...


class PdfParseError(Exception):
    """Raised when the byte stream is not a readable PDF (bad header /
    truncated / broken xref). The wrapper catches this and RETURNS a message
    with error:"corrupt_file" — never an uncaught PdfReadError-style stack
    (MED-RES-02, GOV-RES-01)."""


# ---------------------------------------------------------------------------
# Runtime registries (DP-C §4.3 provider swap without code change)
# ---------------------------------------------------------------------------

_TEXT_REGISTRY: dict[str, PdfTextProvider] = {}
_OCR_REGISTRY: dict[str, OcrProvider] = {}


def register_pdf_text_provider(provider: PdfTextProvider) -> None:
    """Register (or replace) a text provider under its own id. Idempotent."""
    _TEXT_REGISTRY[provider.id] = provider


def get_pdf_text_provider(provider_id: str) -> PdfTextProvider | None:
    """Resolve by id at call time; None when unknown → caller raises
    MediaError("unknown_provider")."""
    return _TEXT_REGISTRY.get(provider_id)


def list_pdf_text_providers() -> list[str]:
    return sorted(_TEXT_REGISTRY)


def register_ocr_provider(provider: OcrProvider) -> None:
    """Register (or replace) an OCR provider under its own id. Idempotent."""
    _OCR_REGISTRY[provider.id] = provider


def get_ocr_provider(provider_id: str) -> OcrProvider | None:
    """Resolve an OCR provider by id at call time; None when unknown."""
    return _OCR_REGISTRY.get(provider_id)


def list_ocr_providers() -> list[str]:
    return sorted(_OCR_REGISTRY)
