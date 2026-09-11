# AUTO-GENERATED — do not edit; source: contracts/media-message.schema.json
# Requirement IDs: MED-01, MED-02
# Generated from DP-C §3.2 (datamodel-codegen TypedDict target shape). Consumers import this
# type; never inline a UnifiedMediaMessage literal elsewhere (CI grep guard, DP-C §8.3).

from typing import Any, Literal, Optional, TypedDict

MediaType = Literal["stt", "vision", "pdf", "tts"]


class UnifiedMediaMessage(TypedDict):
    """MED-01/MED-02 single shared shape for stt|vision|pdf|tts (contract #2)."""

    type: MediaType  # Modality tag; downstream switches only on this tag.
    raw_ref: str  # Input reference (path / stream id / text hash) — never raw bytes.
    text: str  # Extracted or echoed text.
    structured_fields: Optional[dict[str, Any]]  # Free-form payload; null when N/A.
    confidence: float  # 0..1, normalized; 0 when error is not None.
    synthetic: bool  # True iff produced from checked-in synthetic fixture (MED-04).
    timestamp: str  # ISO-8601 UTC when normalization completed.
    provider: str  # Effective provider id, e.g. openai-whisper, synthetic-fixture.
    error: Optional[str]  # None on success; MED-RES-02 typed code on bad input.
    version: Literal["1.0.0"]  # Additive optional field = MINOR; breaking = MAJOR.
