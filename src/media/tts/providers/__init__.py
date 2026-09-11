# Requirement IDs: MED-01, MED-TTS-01, MED-TTS-02, MED-REU-02, XCUT-08
"""TTS provider abstraction + runtime registry — Python mirror of types.ts."""

from .types import (
    TtsChunk,
    TtsFormat,
    TtsInput,
    TtsOptions,
    TtsProvider,
    TtsResult,
    get_tts_provider,
    list_tts_providers,
    register_tts_provider,
)

__all__ = [
    "TtsChunk",
    "TtsFormat",
    "TtsInput",
    "TtsOptions",
    "TtsProvider",
    "TtsResult",
    "get_tts_provider",
    "list_tts_providers",
    "register_tts_provider",
]
