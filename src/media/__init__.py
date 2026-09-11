# Requirement IDs: MED-01, MED-02, MED-03, MED-REU-02, XCUT-07
"""Barrel re-exports ONLY — DP-C §8.1/§8.2.

NOTE: direct entrypoint imports remain the PREFERRED surface
(``from src.media.stt import transcribe`` etc.). Importing from this package
transitively evaluates all four modality providers, which violates MED-REU-02
independent importability — use it only when you genuinely want the whole
media package.
"""

from __future__ import annotations

from src.media.config import (
    MODALITIES,
    MediaError,
    load_media_config,
    resolve_credential,
)
from src.media.resilient import with_media_resilience

from src.media.stt import (
    AudioInput as SttAudioInput,
    SttOptions,
    add_stt_provider,
    transcribe,
)

from src.media.vision import (
    ImageInput as VisionImageInput,
    VisionOptions,
    add_vision_provider,
    caption,
    resolve_prompt,
)

__all__ = [
    # config (public surface of config.py; TS additionally exposes
    # MEDIA_SAFE_DEFAULTS/warn/isModalityKey — not public in the Python module)
    "MODALITIES",
    "MediaError",
    "load_media_config",
    "resolve_credential",
    # resilient
    "with_media_resilience",
    # stt
    "SttAudioInput",
    "SttOptions",
    "add_stt_provider",
    "transcribe",
    # vision
    "VisionImageInput",
    "VisionOptions",
    "add_vision_provider",
    "caption",
    "resolve_prompt",
]

from src.media.pdf import (
    PdfInput as PdfDocumentInput,
    add_ocr_provider,
    add_pdf_text_provider,
    extract,
)

from src.media.tts import (
    BargeInController,
    TtsChunk,
    TtsInput,
    TtsInputError,
    TtsOptions as TtsSynthesisOptions,
    add_tts_provider,
    synthesize,
    synthesize_stream,
)

__all__ += [
    # pdf
    "PdfDocumentInput",
    "add_ocr_provider",
    "add_pdf_text_provider",
    "extract",
    # tts
    "BargeInController",
    "TtsChunk",
    "TtsInput",
    "TtsInputError",
    "TtsSynthesisOptions",
    "add_tts_provider",
    "synthesize",
    "synthesize_stream",
]
