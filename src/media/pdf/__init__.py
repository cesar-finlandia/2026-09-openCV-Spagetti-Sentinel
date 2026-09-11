# Requirement IDs: MED-01, MED-02, MED-03, MED-04, MED-REU-01, MED-REU-02,
# MED-RES-01, MED-RES-02, RES-REU-02, GOV-RES-01, GOV-RES-04, XCUT-08
"""PDF public entrypoint (Python) — DP-C §4.3 (text extraction + OCR fallback).

Layout note: this entrypoint is the PACKAGE ``src/media/pdf/`` rather than a
``pdf.py`` module because the design-plan tree also places ``pdf/providers/``
and ``pdf/ocr/`` beside it and a same-named module+package cannot coexist in
one directory. ``from src.media.pdf import extract`` behaves exactly like the
TS ``import { extract } from "src/media/pdf"``.

extract(input, opts?) implements the §4.3 algorithm EXACTLY:
  1. PdfTextProvider.extract_text(input)          — text layer first
  2. per page trimmed length < ocr_threshold      — OCR step when available,
     else keep short text with ocr_used False and LOWERED confidence
  3. concatenate page texts → result["text"]
  4. confidence = weighted mean of page confidences (OCR pages lower)
  5. structured_fields {page_count, extraction_mode, pages[], ocr_provider}

§7.2 error contract: bad-input codes (empty_input | corrupt_file |
unsupported_format) are RETURNED as UnifiedMediaMessage["error"] with NO
provider call; parse-shaped provider failures map to corrupt_file; every
other provider failure RAISES normalized MediaError so RES-01 can
retry/fallback. OCR-binary-missing degrades gracefully (GOV-RES-04):
text-layer result, ocr_provider:"none", no raise.

Isolation (MED-REU-02 / DP-C §8.1): imports ONLY media-message types, media
config, its own pdf.providers/* and pdf.ocr/* — NEVER stt/vision/tts.
"""

from __future__ import annotations

import asyncio
import base64 as _b64
import datetime as _dt
from pathlib import Path
from typing import Any

from src.media.config import MediaError, load_media_config
from src.media.media_message import UnifiedMediaMessage

from .providers.types import (
    PdfParseError,
    get_ocr_provider,
    get_pdf_text_provider,
    register_ocr_provider,
    register_pdf_text_provider,
)
from .providers import pypdf as _pypdf_provider
from .providers import synthetic_fixture as _pdf_synthetic_fixture
from .ocr import none as _ocr_none
from .ocr import synthetic_fixture as _ocr_synthetic_fixture
from .ocr import tesseract as _ocr_tesseract

__all__ = [
    "add_ocr_provider",
    "add_pdf_text_provider",
    "extract",
    "extract_async",
    "extract_sync",
    "validate_pdf_buffer",
    "PdfInput",  # re-exported dict alias from providers.types
]

# Re-export PdfInput for callers that want the type visible at the entrypoint.
from .providers.types import PdfInput  # noqa: E402,F401

DEFAULT_OCR_THRESHOLD_CHARS = 40


def add_pdf_text_provider(provider: Any) -> None:
    """Register an additional TEXT provider at runtime (Engine backends)."""
    register_pdf_text_provider(provider)


def add_ocr_provider(provider: Any) -> None:
    """Register an additional OCR provider at runtime (Engine backends)."""
    register_ocr_provider(provider)


# ---------------------------------------------------------------------------
# Built-in registration (DP-C §4.3 — synthetic-fixture ALWAYS available)
# ---------------------------------------------------------------------------

_pdf_synthetic_fixture.register()
_pypdf_provider.register()
_ocr_tesseract.register()
_ocr_none.register()
_ocr_synthetic_fixture.register()


# ---------------------------------------------------------------------------
# Input materialization + validation (MED-RES-02 / §4.3 failure table)
# ---------------------------------------------------------------------------


def _materialize_bytes(pdf: PdfInput) -> bytes:
    if isinstance(pdf, dict):
        if "buffer" in pdf:
            return bytes(pdf["buffer"])
        if "base64" in pdf:
            return _b64.b64decode(pdf["base64"])
        if "path" in pdf:
            return Path(pdf["path"]).read_bytes()
    raise MediaError("provider_error", "pdf input must carry path|buffer|base64")


def _raw_ref_of(pdf: PdfInput) -> str:
    if isinstance(pdf, dict):
        if "path" in pdf:
            return str(pdf["path"])
        if "buffer" in pdf:
            return f"buffer:{len(pdf['buffer'])}b"
    return "base64:inline"


def validate_pdf_buffer(pdf: PdfInput, data: bytes) -> str | None:
    """Per the §4.3 failure table: zero bytes → empty_input; non-.pdf document
    (e.g. .docx) → unsupported_format; bad/missing %PDF header → corrupt_file.
    Returns None when OK."""
    if len(data) == 0:
        return "empty_input"
    ext = ""
    if isinstance(pdf, dict) and "path" in pdf:
        name = Path(str(pdf["path"])).name
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in ("", "pdf"):
        return "unsupported_format"
    if data[:5] != b"%PDF-":
        return "corrupt_file"
    return None


# ---------------------------------------------------------------------------
# OCR provider resolution (§4.3 two-layer pairing)
# ---------------------------------------------------------------------------


def _resolve_ocr_provider(config: dict, opts: dict, text_provider_id: str):
    """Fixture note (DP-C §4.3): when the text layer is the checked-in synthetic
    fixture, the OCR step is served by the synthetic-fixture OCR provider —
    extract.json text, NO binary needed for offline CI. Otherwise the configured
    id (default tesseract per config/media.json) is resolved and availability-
    probed; a missing binary → None so the caller degrades gracefully
    (GOV-RES-04), never raises."""
    requested = (opts.get("ocr_provider") or config.get("ocr_provider") or "none") or "none"
    if requested == "none":
        return None
    # Offline fixture pairing — deterministic MED-AC-01 OCR fallback path.
    if text_provider_id == "synthetic-fixture" and requested == "tesseract":
        synthetic = get_ocr_provider("synthetic-fixture")
        if synthetic is not None and synthetic.available():
            return synthetic
    provider = get_ocr_provider(requested)
    if provider is None or not provider.available():
        return None  # graceful degrade
    return provider


def _clamp01(value: float) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.0
    return min(1.0, max(0.0, v))


# ---------------------------------------------------------------------------
# extract / extract_sync / extract_async (DP-C §4.3/§7.2)
# ---------------------------------------------------------------------------


def _error_message(raw_ref: str, provider: str, code: str) -> UnifiedMediaMessage:
    return {
        "type": "pdf",
        "raw_ref": raw_ref,
        "text": "",
        "structured_fields": None,
        "confidence": 0,
        "synthetic": False,
        "timestamp": _dt.datetime.now(_dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "provider": provider,
        "error": code,
        "version": "1.0.0",
    }


def _finalize(
    raw_ref: str,
    provider_id: str,
    pages: list[dict],
    ocr_provider_id: str,
    degraded_ocr: bool,
) -> UnifiedMediaMessage:
    """§4.3 steps 3–5: concatenate texts, mean confidence, structured_fields."""
    if pages and all(p["ocr_used"] for p in pages):
        extraction_mode = "ocr_only"
    elif any(p["ocr_used"] for p in pages):
        extraction_mode = "text_then_ocr"
    else:
        extraction_mode = "text_only"
    confidence = (
        sum(p["confidence"] for p in pages) / len(pages) if pages else 0.0
    )
    return {
        "type": "pdf",
        "raw_ref": raw_ref,
        "text": "\n".join(p["text"] for p in pages),
        "structured_fields": {
            "page_count": len(pages),
            "extraction_mode": extraction_mode,
            "pages": [
                {
                    "page": p["page"],
                    "text": p["text"],
                    "ocr_used": p["ocr_used"],
                    "confidence": _clamp01(p["confidence"]),
                }
                for p in pages
            ],
            # §7.2 GOV-RES-04 row: binary missing → reported as "none".
            "ocr_provider": "none" if degraded_ocr else ocr_provider_id,
            **({"ocr_degraded": True} if degraded_ocr else {}),
        },
        "confidence": _clamp01(confidence),
        # MED-04/NONGOAL-06 provenance: true iff produced by the checked-in
        # synthetic fixture provider.
        "synthetic": provider_id == "synthetic-fixture",
        "timestamp": _dt.datetime.now(_dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "provider": provider_id,
        "error": None,
        "version": "1.0.0",
    }


def _run_pipeline(pdf: PdfInput, opts: dict, config: dict, raw_ref: str, threshold: int) -> UnifiedMediaMessage:
    # Step 1: text layer first (fast path for born-digital PDFs).
    text_provider = get_pdf_text_provider(config["provider"])
    if text_provider is None:
        raise MediaError(
            "unknown_provider",
            f'no PDF text provider registered under id "{config["provider"]}"',
        )
    try:
        text_result = dict(text_provider.extract_text(pdf))
    except (MediaError, PdfParseError):
        raise
    except Exception as err:
        raise MediaError(
            "provider_error", f'pdf provider "{text_provider.id}" failed: {err}'
        ) from err

    # Step 2: OCR pass on pages below the threshold.
    ocr = _resolve_ocr_provider(config, opts, text_provider.id)
    reported_ocr_id = ocr.id if ocr is not None else "none"
    requested_ocr = (opts.get("ocr_provider") or config.get("ocr_provider") or "none") or "none"
    degraded_ocr = ocr is None and requested_ocr != "none"

    pages: list[dict] = []
    for p in text_result.get("text_by_page", []):
        page_text = str(p.get("text", ""))
        short = len(page_text.strip()) < threshold
        if short and ocr is not None:
            try:
                result = dict(ocr.ocr(_materialize_bytes(pdf), opts))
                pages.append(
                    {
                        "page": p["page"],
                        "text": str(result.get("text", "")),
                        "ocr_used": True,
                        "confidence": _clamp01(result.get("confidence", 0)),
                    }
                )
                continue
            except MediaError:
                raise
            except Exception as err:
                raise MediaError(
                    "provider_error", f'pdf ocr provider "{ocr.id}" failed: {err}'
                ) from err
        # No OCR engine (disabled or unavailable) → keep short text with
        # lowered confidence; ocr_used stays False (§4.3 step 2 else-branch).
        confidence = _clamp01(text_result.get("confidence", 0))
        pages.append(
            {
                "page": p["page"],
                "text": page_text,
                "ocr_used": False,
                "confidence": min(confidence, 0.35) if short else confidence,
            }
        )

    return _finalize(raw_ref, config["provider"], pages, reported_ocr_id, degraded_ocr)


def extract_sync(pdf: PdfInput, opts: dict | None = None) -> UnifiedMediaMessage:
    """Synchronous extract (DP-C §4.3). Bad input → message with typed `error`
    code and NO provider call; parse-shaped failures → corrupt_file message;
    other provider failure → raised MediaError."""
    config = load_media_config("pdf", opts or None)
    raw_ref = _raw_ref_of(pdf)
    # Extension check comes FIRST so unsupported formats never touch disk.
    ext = ""
    if isinstance(pdf, dict) and "path" in pdf:
        name = Path(str(pdf["path"])).name
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in ("", "pdf"):
        return _error_message(raw_ref, config["provider"], "unsupported_format")
    try:
        data = _materialize_bytes(pdf)
    except MediaError:
        raise
    except Exception as err:
        raise MediaError("provider_error", f"pdf input could not be read: {err}") from err
    bad_code = validate_pdf_buffer(pdf, data)
    if bad_code is not None:
        return _error_message(raw_ref, config["provider"], bad_code)
    threshold = int(opts.get("ocr_threshold_chars", opts.get("ocrThresholdChars", DEFAULT_OCR_THRESHOLD_CHARS))) if opts else DEFAULT_OCR_THRESHOLD_CHARS
    try:
        return _run_pipeline(pdf, opts or {}, config, raw_ref, threshold)
    except PdfParseError:
        # §4.3 failure table: parse-shaped errors map to corrupt_file.
        return _error_message(raw_ref, config["provider"], "corrupt_file")


def extract(pdf: PdfInput, opts: dict | None = None) -> UnifiedMediaMessage:
    """Blocking convenience alias of extract_sync — mirrors the DP-C §9.1
    Python usage ``msg = extract({"path": ...}, {"provider": ...})``.
    Use extract_async for timeout-bounded network providers."""
    return extract_sync(pdf, opts)


async def extract_async(pdf: PdfInput, opts: dict | None = None) -> UnifiedMediaMessage:
    """Timeout-bounded async extract — never silent hang (§7.2)."""
    config = load_media_config("pdf", opts or None)
    return await asyncio.wait_for(
        asyncio.to_thread(extract_sync, pdf, opts), timeout=config["timeout_ms"]
    )
