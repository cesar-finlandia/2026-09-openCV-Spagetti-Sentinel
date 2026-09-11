# Requirement IDs: MED-TTS-02 | DP-C §5.2
"""Barge-in / interruption controller — Python asyncio.Event variant of bargeIn.ts.

Mechanics only: NONGOAL-04 forbids any dialogue policy, so this class exposes
cancellation state and nothing else.

Semantics (§5.2): interrupt() cancels GENERATION of further TtsChunks —
synthesize_stream honours the event between chunks and raises
asyncio.CancelledError. Playback of already-emitted bytes is the audio sink's
responsibility (stop_and_clear); the wrapper guarantees no further audio_chunk
after abort.
"""

from __future__ import annotations

import asyncio


class BargeInController:
    """Cancellation token for in-flight TTS synthesis (DP-C §5.2)."""

    def __init__(self) -> None:
        self._event = asyncio.Event()
        self.reason: str | None = None

    @property
    def signal(self) -> asyncio.Event:
        """Token passed to synthesize_stream opts["signal"] (§5.2)."""
        return self._event

    def interrupt(self, reason: str = "barge_in") -> None:
        """Cancel in-flight synthesis; idempotent, records first reason."""
        if not self._event.is_set():
            self.reason = reason
        self._event.set()

    def is_interrupted(self) -> bool:
        """True once interrupt() has fired (or the event was set externally)."""
        return self._event.is_set()
