// Requirement IDs: MED-01, MED-TTS-01, MED-TTS-02, MED-REU-02, RES-03,
// GOV-MIN-04, XCUT-08
// TTS provider abstraction + runtime registry — DP-C §4.4.
//
// Providers implement TtsProvider and register themselves via
// registerTtsProvider(); the wrapper resolves getTtsProvider(config.provider)
// AT CALL TIME so MED_TTS_PROVIDER env swaps need zero code change (MED-03).
// A missing id returns null → wrapper throws MediaError("unknown_provider")
// per DP-C §7.2 (never silently falls back).
//
// synthesizeStream is OPTIONAL: request/response providers (openai-tts today)
// omit it and the wrapper polyfills streaming by slicing the synthesized bytes
// into 4KB base64 chunks (DP-C §5.1); native-streaming providers (elevenlabs)
// implement it and the wrapper delegates verbatim.
//
// NONGOAL-04: voice is a provider voice-id passthrough (e.g. "alloy"). No
// persona/tone/dialogue-policy logic lives anywhere under src/media/tts.
//
// Isolation (MED-REU-02): imports only media shared surfaces (config) — never
// stt/vision/pdf (CI grep guard, DP-C §8.1).

import type { MediaConfig } from "../../config.js";

/** Text to synthesize: bare string (1..5000 chars) or { text, voice? }. */
export type TtsInput = string | { text: string; voice?: string };

/** Supported output formats (anything else → error "unsupported_format"). */
export type TtsFormat = "mp3" | "wav" | "pcm";

/** Per-wrapper options: MediaConfig slice + §4.4 fields. */
export type TtsOptions = Partial<MediaConfig> & {
  /** Provider-specific voice id passthrough (e.g. "alloy", "nova") — never a persona. */
  voice?: string;
  /** Output container format (default mp3). */
  format?: TtsFormat;
  /** Output sample rate hint, e.g. 24000. */
  sampleRate?: number;
  /** Barge-in cancellation token (DP-C §5.2); checked before every yield. */
  signal?: AbortSignal;
};

/** One incremental audio chunk yielded by synthesizeStream (MED-TTS-01). */
export interface TtsChunk {
  /** Base64-encoded partial audio; caller pipes Buffer.from(chunk,"base64") to its sink. */
  audio_chunk: string;
  /** Text span this chunk covers; "" when unavailable (polyfill). */
  delta_text: string;
  index: number;
  is_final: boolean;
  /** Measured ms to this chunk (final chunk carries MED-TTS-03 latency). */
  latency_ms?: number;
}

/** Normalized non-streaming provider result — wrapper maps onto UnifiedMediaMessage. */
export interface TtsResult {
  audio: Uint8Array;
  format: string;
  sampleRate: number;
  /** Estimated/known duration of the synthesized audio (ms). */
  duration_ms?: number;
  /** Stable reference for provenance (fixture path); null → inline base64. */
  audio_ref?: string | null;
}

/**
 * One text-to-speech backend. Implementations MUST throw on failure (network,
 * rate limit, missing credentials) so RES-01 can retry/fallback (RES-REU-02);
 * they never return error-bearing results for provider-side problems.
 */
export interface TtsProvider {
  /** Lowercase kebab-case id: "openai-tts" | "elevenlabs" | "synthetic-fixture". */
  readonly id: string;
  synthesize(input: TtsInput, opts: TtsOptions): Promise<TtsResult>;
  /** Native incremental delivery; omitting it makes the wrapper polyfill (§5.1). */
  synthesizeStream?(input: TtsInput, opts: TtsOptions): AsyncIterable<TtsChunk>;
}

//#region Runtime registry (DP-C §4.4 provider swap without code change)

const REGISTRY = new Map<string, TtsProvider>();

/** Register (or replace) a provider under its own id. Idempotent per id. */
export function registerTtsProvider(p: TtsProvider): void {
  REGISTRY.set(p.id, p);
}

/** Resolve by id at call time; null when unknown → caller throws
 * MediaError("unknown_provider") (DP-C §7.2 malformed-config row). */
export function getTtsProvider(id: string): TtsProvider | null {
  return REGISTRY.get(id) ?? null;
}

/** All registered ids (diagnostics/tests only — never used for resolution). */
export function listTtsProviders(): string[] {
  return [...REGISTRY.keys()].sort();
}

//#endregion
