# Requirement IDs: MED-03, MED-RES-01, MED-RES-02, GOV-MIN-04, GOV-RES-01 | DP-C §4.3/§10.1
"""pypdf PDF text provider — DP-C §4.3 built-in (Python default per §10.1).

Optional-dep style (GOV-MIN-04): ``pypdf`` is imported LAZILY on first call;
an absent library surfaces as a RAISED MediaError at call time so RES-01 can
retry/fallback — never a startup crash. pypdf's PdfReadError-family failures
are normalized to PdfParseError so the wrapper maps them to
error:"corrupt_file" (§4.3 failure table — never an uncaught stack).
"""

from __future__ import annotations

import base64 as _b64
import io
from pathlib import Path

from src.media.config import MediaError

from .types import PdfInput, PdfParseError, PdfTextProvider, register_pdf_text_provider

_pypdf_module = None


def _require_pypdf():
    global _pypdf_module
    if _pypdf_module is not None:
        return _pypdf_module
    try:
        import pypdf as module  # optional dep — loaded only when selected
    except Exception as err:  # pragma: no cover - depends on environment
        raise MediaError("provider_error", f"pypdf unavailable for provider pypdf ({err})") from err
    _pypdf_module = module
    return module


def _materialize_bytes(pdf: PdfInput) -> bytes:
    if isinstance(pdf, dict):
        if "buffer" in pdf:
            return bytes(pdf["buffer"])
        if "base64" in pdf:
            return _b64.b64decode(pdf["base64"])
        if "path" in pdf:
            return Path(pdf["path"]).read_bytes()
    raise MediaError("provider_error", "pdf input must carry path|buffer|base64")


def _is_parse_error(err: Exception) -> bool:
    name = type(err).__name__
    return name in {
        "PdfReadError",
        "EmptyFileError",
        "InvalidPdfError",
        "DependencyError",
        "ParseError",
    } or isinstance(err, PdfParseError)


class PypdfTextProvider:
    id = "pypdf"

    def extract_text(self, pdf: PdfInput) -> dict:
        pypdf = _require_pypdf()
        data = _materialize_bytes(pdf)
        try:
            reader = pypdf.PdfReader(io.BytesIO(data))
            text_by_page = []
            for index, page in enumerate(reader.pages, start=1):
                text = " ".join((page.extract_text() or "").split())
                text_by_page.append({"page": index, "text": text.strip()})
        except MediaError:
            raise
        except PdfParseError:
            raise
        except Exception as err:
            if _is_parse_error(err):
                raise PdfParseError(f"pypdf could not parse document: {err}") from err
            raise MediaError("provider_error", f"pypdf provider failed: {err}") from err
        return {"text_by_page": text_by_page, "confidence": 0.9}


_INSTANCE = PypdfTextProvider()


def register() -> None:
    """Self-register so get_pdf_text_provider('pypdf') works after import."""
    register_pdf_text_provider(_INSTANCE)


pypdf_text_provider = _INSTANCE
