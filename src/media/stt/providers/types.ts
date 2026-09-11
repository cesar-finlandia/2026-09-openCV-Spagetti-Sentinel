// Requirement IDs: MED-01, MED-03, MED-REU-02, RES-03, GOV-MIN-04, XCUT-08
// STT provider abstraction + runtime registry — DP-C §4.1.
//
// Providers implement SttProvider and register themselves via
// registerSttProvider(); the wrapper resolves getSttProvider(config.provider)
// AT CALL TIME so MED_STT_PROVIDER env swaps need zero code change (MED-03).
// A missing id returns null → wrapper throws MediaError("unknown_provider")
// per DP-C §7.2 (never silently falls back).
//
// Isolation (MED-REU-02): this file imports nothing outside src/media shared
// surfaces (media-message/config types) — never vision/pdf/tts (CI grep guard,
// DP-C §8.1).

import type { MediaConfig } from "../../config.js";

/** Raw audio input variants accepted by transcribe() — DP-C §4.1 AudioInput.
 * Exactly one variant key must be present; encoding defaults to sniffing /
 * path extension when omitted. */
export type AudioInput =
  | { path: string }
  | { buffer: Uint8Array; encoding?: string }
  | { stream: NodeJS.ReadableStream; encoding?: string }
  | { base64: string; encoding?: string };

/** Per-wrapper options: MediaConfig slice + generic hints only (MED-REU-01 —
 * no persona/domain vocabulary; promptHint defaults to undefined). */
export type SttOptions = Partial<MediaConfig> & {
  /** Language hint, e.g. "en". Generic hint only. */
  language?: string;
  /** Generic verbatim hint, e.g. "transcribe verbatim". Not domain-tuned. */
  promptHint?: string;
};

/** Normalized provider result — wrapper maps it onto UnifiedMediaMessage. */
export interface SttResult {
  text: string;
  /** Confidence normalized to 0..1. */
  confidence: number;
  /** language / duration_ms / words[] payload, or null when unavailable. */
  structured: Record<string, unknown> | null;
}

/**
 * One speech-to-text backend. Implementations MUST throw on failure (network,
 * rate limit, missing credentials) so RES-01 can retry/fallback (RES-REU-02);
 * they never return error-bearing results for provider-side problems.
 */
export interface SttProvider {
  /** Lowercase kebab-case id, e.g. "openai-whisper", "synthetic-fixture". */
  readonly id: string;
  transcribe(input: AudioInput, opts: SttOptions): Promise<SttResult>;
}

//#region Runtime registry (DP-C §4.1 provider swap without code change)

const REGISTRY = new Map<string, SttProvider>();

/** Register (or replace) a provider under its own id. Idempotent per id. */
export function registerSttProvider(p: SttProvider): void {
  REGISTRY.set(p.id, p);
}

/** Resolve by id at call time; null when unknown → caller throws
 * MediaError("unknown_provider") (DP-C §7.2 malformed-config row). */
export function getSttProvider(id: string): SttProvider | null {
  return REGISTRY.get(id) ?? null;
}

/** All registered ids (diagnostics/tests only — never used for resolution). */
export function listSttProviders(): string[] {
  return [...REGISTRY.keys()].sort();
}

//#endregion
