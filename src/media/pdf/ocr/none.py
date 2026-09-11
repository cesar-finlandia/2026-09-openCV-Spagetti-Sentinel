# Requirement IDs: GOV-RES-04, MED-RES-02, XCUT-08
""""none" OCR provider — DP-C §4.3 built-in.

Explicit disabled marker: the wrapper checks id == "none" BEFORE invoking
ocr(), so ocr() here is a hard guard only. Selecting "none" means scanned
pages keep their short text-layer content with ocr_used:false and lowered
confidence — graceful degrade, never a crash (GOV-RES-04).
"""

from __future__ import annotations

from src.media.config import MediaError

from ..providers.types import OcrProvider, PdfOptions, register_ocr_provider


class NoneOcrProvider:
    id = "none"

    def available(self) -> bool:
        # "Available" as a registry citizen; the wrapper still treats id
        # "none" as OCR-disabled before ever calling ocr().
        return True

    def ocr(self, page_image: bytes, opts: PdfOptions | None = None) -> dict:
        raise MediaError("provider_error", 'OCR is disabled (ocr_provider "none")')


_INSTANCE = NoneOcrProvider()


def register() -> None:
    """Self-register so get_ocr_provider('none') works after import."""
    register_ocr_provider(_INSTANCE)


none_ocr_provider = _INSTANCE
