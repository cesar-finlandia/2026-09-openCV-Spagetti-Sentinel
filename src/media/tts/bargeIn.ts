// Requirement IDs: MED-TTS-02 | DP-C §5.2
// Barge-in / interruption controller — standard AbortController/AbortSignal,
// no bespoke token. Mechanics only: NONGOAL-04 forbids any dialogue policy,
// so this class exposes cancellation state and nothing else.
//
// Semantics (§5.2): interrupt() cancels GENERATION of further TtsChunks —
// synthesizeStream checks signal.aborted before every yield and throws
// DOMException("Aborted", "AbortError"). Playback of already-emitted bytes is
// the audio sink's responsibility (stopAndClear); the wrapper guarantees no
// further audio_chunk after abort.

export class BargeInController {
  readonly controller: AbortController;

  constructor() {
    this.controller = new AbortController();
  }

  /** Cancellation token passed to synthesizeStream opts.signal (§5.2). */
  get signal(): AbortSignal {
    return this.controller.signal;
  }

  /** Cancel in-flight synthesis; reason defaults to "barge_in". Idempotent. */
  interrupt(reason?: string): void {
    if (!this.signal.aborted) this.controller.abort(reason ?? "barge_in");
  }

  /** True once interrupt() has fired (or the signal was aborted externally). */
  isInterrupted(): boolean {
    return this.signal.aborted;
  }

  /**
   * Convenience wiring for a new user-input event: interrupts with reason
   * "new_input". Optional per DP-C §5.2 — callers may prefer explicit
   * interrupt("user_spoke") from their own input stream handler.
   */
  onNewInput(_input?: unknown): void {
    this.interrupt("new_input");
  }
}
