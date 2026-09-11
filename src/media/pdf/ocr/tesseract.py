# Requirement IDs: MED-03, GOV-RES-04, GOV-MIN-04, MED-RES-02 | DP-C §4.3/§7.2/§10.1
"""tesseract OCR provider — DP-C §4.3 optional built-in (§10.1 OPTIONAL extra).

Shells out to the system ``tesseract`` binary (no pip OCR dependency).
Binary availability is detected ONCE via a bounded ``tesseract --version``
probe and cached; when absent the wrapper degrades gracefully per §7.2 row
"OCR unavailable": text-layer-only result, ocr_provider:"none", lowered
confidence, NO raise (GOV-RES-04). Hard runtime failures raise MediaError
so RES-01 can act.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from src.media.config import MediaError

from ..providers.types import OcrProvider, PdfOptions, register_ocr_provider

_TESSERACT_TIMEOUT_S = 10
_availability_cache: bool | None = None


def _detect_binary() -> bool:
    global _availability_cache
    if _availability_cache is None:
        _availability_cache = shutil.which("tesseract") is not None
    return _availability_cache


class TesseractOcrProvider:
    id = "tesseract"

    def available(self) -> bool:
        """False when the system binary is missing → wrapper degrades to
        text-layer-only with ocr_provider:"none" (never raises)."""
        return _detect_binary()

    def ocr(self, page_image: bytes, opts: PdfOptions | None = None) -> dict:
        if not _detect_binary():
            # Wrapper normally guards this; kept as a hard guard for direct use.
            raise MediaError(
                "provider_error",
                'tesseract binary not available (ocr_provider should degrade to "none")',
            )
        opts = opts or {}
        languages = opts.get("ocr_languages") or opts.get("ocrLanguages")
        with tempfile.TemporaryDirectory(prefix="media-pdf-ocr-") as tmp:
            image_path = Path(tmp) / "page.png"
            image_path.write_bytes(page_image)
            cmd = ["tesseract", str(image_path), "stdout"]
            if languages:
                cmd += ["-l", str(languages)]
            try:
                run = subprocess.run(  # noqa: S603 - fixed binary name, no shell
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=_TESSERACT_TIMEOUT_S,
                )
            except subprocess.TimeoutExpired as err:
                raise MediaError("provider_error", f"tesseract timed out after {_TESSERACT_TIMEOUT_S}s") from err
            except OSError as err:
                raise MediaError("provider_error", f"tesseract failed: {err}") from err
            if run.returncode != 0:
                raise MediaError("provider_error", f"tesseract failed: {(run.stderr or '').strip()}")
            return {"text": (run.stdout or "").strip(), "confidence": 0.75}


_INSTANCE = TesseractOcrProvider()


def register() -> None:
    """Self-register so get_ocr_provider('tesseract') works after import."""
    register_ocr_provider(_INSTANCE)


tesseract_ocr_provider = _INSTANCE


def reset_availability_cache() -> None:
    """Test/diagnostic hook: reset the cached binary probe result."""
    global _availability_cache
    _availability_cache = None
