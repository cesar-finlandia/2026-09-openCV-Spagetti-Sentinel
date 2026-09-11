// Requirement IDs: MED-01, MED-02, MED-TTS-01, MED-TTS-02, MED-TTS-03,
// MED-REU-01, MED-REU-02, MED-RES-01, MED-RES-02, RES-REU-02, GOV-RES-01,
// GOV-RES-04, XCUT-08
// TTS public entrypoint — DP-C §4.4 (synthesize) + §5.1 (synthesizeStream).
//
// synthesize(input, opts?) applies the §7.2/§4.4 error contract: bad inputs
// (empty, >5000 chars, unsupported format) are RETURNED as UnifiedMediaMessage
// with a typed error BEFORE any provider call; provider failures are THROWN as
// MediaError so RES-01 can retry/fallback. The provider resolves at call time
// via getTtsProvider(config.provider) (MED_TTS_PROVIDER env swap, zero code
// change) and every path is timeout-bounded (default 15000 — never silent hang).
//
// synthesizeStream(input, opts?) yields incremental TtsChunks (MED-TTS-01):
// native provider streaming is delegated verbatim; request/response providers
// are polyfilled by slicing the synthesized bytes into 4KB base64 chunks.
// opts.signal is checked BEFORE every yield (and before the provider fetch);
// abort throws DOMException("Aborted","AbortError") which callers map to a
// final error:"tts_interrupted" envelope (§5.2 — see ./tts/README.md).
//
// Isolation (MED-REU-02 / DP-C §8.1): imports ONLY media-message types, media
// config, its own tts/providers/* + bargeIn — NEVER stt/vision/pdf.
//
// NONGOAL-04: voice is a provider voice-id passthrough; no dialogue policy,
// persona, or tone logic exists anywhere in this module.

import { createHash } from "node:crypto";
import { loadMediaConfig, MediaError } from "./config.js";
import type { UnifiedMediaMessage } from "./media-message.js";
import { registerTtsProvider } from "./tts/providers/types.js";
import type { TtsChunk, TtsFormat, TtsInput, TtsOptions, TtsProvider, TtsResult } from "./tts/providers/types.js";
import { getTtsProvider } from "./tts/providers/types.js";
import * as syntheticFixture from "./tts/providers/synthetic-fixture.js";
import * as openaiTts from "./tts/providers/openai-tts.js";
import * as elevenlabs from "./tts/providers/elevenlabs.js";

export { BargeInController } from "./tts/bargeIn.js";
export type { TtsChunk, TtsFormat, TtsInput, TtsOptions } from "./tts/providers/types.js";

//#region Built-in registration (DP-C §4.4 — synthetic-fixture ALWAYS available)

syntheticFixture.register();
openaiTts.register();
elevenlabs.register();

/** Register an additional provider at runtime (Engine-supplied backends). */
export function addTtsProvider(p: Parameters<typeof registerTtsProvider>[0]): void {
  registerTtsProvider(p);
}

//#endregion

//#region Input validation (§4.4 failure table / MED-RES-02)

const MAX_TEXT_CHARS = 5000;
const SUPPORTED_FORMATS = new Set(["mp3", "wav", "pcm"]);

/** Typed error thrown by synthesizeStream for bad input — a stream has no
 * envelope channel mid-flight, so §4.4 bad-input codes surface here as
 * exceptions; callers wanting UnifiedMediaMessage envelopes use synthesize(). */
export class TtsInputError extends Error {
  readonly code: "empty_input" | "unsupported_format";
  constructor(code: "empty_input" | "unsupported_format", message?: string) {
    super(message ?? code);
    this.name = "TtsInputError";
    this.code = code;
  }
}

function textOf(input: TtsInput | null | undefined): string | null {
  if (typeof input === "string") return input;
  if (input && typeof input === "object") return typeof input.text === "string" ? input.text : null;
  return null;
}

/**
 * Validate one TtsInput per the §4.4 failure table. Returns null when OK,
 * otherwise the UnifiedMediaMessage error code to report:
 * "" / null text → empty_input; >5000 chars → unsupported_format (no silent
 * truncation); format outside mp3|wav|pcm → unsupported_format.
 */
export function validateTtsInput(
  input: TtsInput | null | undefined,
  opts?: Pick<TtsOptions, "format"> | null,
): "empty_input" | "unsupported_format" | null {
  const text: string | null = textOf(input ?? null);
  if (text === null || text.length === 0) return "empty_input";
  if (text.length > MAX_TEXT_CHARS) return "unsupported_format"; // caller may split
  const fmt = opts?.format;
  if (fmt !== undefined && !SUPPORTED_FORMATS.has(fmt)) return "unsupported_format";
  return null;
}

function rawRefOf(text: string): string {
  const hash = createHash("sha256").update(text, "utf8").digest("hex").slice(0, 8);
  return `hash:${hash}:text:${text.slice(0, 64)}`;
}

//#endregion

//#region message construction (UnifiedMediaMessage literal — schema §3.1/§3.3)

interface MessageArgs {
  rawRef: string;
  provider: string;
  text: string;
  structuredFields?: Record<string, unknown> | null;
  confidence?: number;
  synthetic?: boolean;
  error?: string | null;
}

function message(args: MessageArgs): UnifiedMediaMessage {
  return {
    type: "tts",
    raw_ref: args.rawRef,
    text: args.text,
    structured_fields: args.structuredFields ?? null,
    confidence: args.confidence ?? 0,
    synthetic: args.synthetic ?? false,
    timestamp: new Date().toISOString(),
    provider: args.provider,
    error: args.error ?? null,
    version: "1.0.0",
  };
}

function errorMessage(rawRef: string, providerId: string, code: NonNullable<UnifiedMediaMessage["error"]>, text = ""): UnifiedMediaMessage {
  return message({ rawRef, provider: providerId, text, error: code });
}

function finalize(input: TtsInput, providerId: string, result: TtsResult, latencyMs: number): UnifiedMediaMessage {
  const text = typeof input === "string" ? input : input.text;
  const structured: Record<string, unknown> = {
    audio_format: result.format,
    sample_rate: result.sampleRate,
    duration_ms: result.duration_ms ?? null,
    chunk_index: 0,
    is_final: true,
    ...(result.audio_ref ? { audio_ref: result.audio_ref } : { audio_base64: Buffer.from(result.audio).toString("base64") }),
    latency_ms: latencyMs,
    barge_in_supported: true,
  };
  return message({
    rawRef: rawRefOf(text),
    provider: providerId,
    text,
    structuredFields: structured,
    confidence: 1.0,
    synthetic: providerId === "synthetic-fixture",
  });
}

//#endregion

//#region synthesize (async main path — DP-C §4.4)

/**
 * Synthesize text to one UnifiedMediaMessage (type:"tts", text echoes input).
 *
 * - Bad input → RESOLVED message with error empty_input|unsupported_format,
 *   confidence 0, NO provider call (§4.4 failure table, MED-RES-02).
 * - Unknown provider id → THROWS MediaError("unknown_provider") (§7.2).
 * - Provider/network failure → THROWS normalized MediaError("provider_error")
 *   so RES-01 can retry/fallback (MED-RES-01); never swallowed into .error.
 * - Every path bounded by timeout_ms (default 15000).
 */
export async function synthesize(input: TtsInput, opts?: TtsOptions): Promise<UnifiedMediaMessage> {
  const config = loadMediaConfig("tts", opts ?? null);

  // 1. Validate BEFORE any provider work (no provider call on bad input).
  const badCode = validateTtsInput(input, opts);
  const rawRef = rawRefOf(textOf(input) ?? "");
  if (badCode === "empty_input") return errorMessage(rawRef, config.provider, "empty_input");
  if (badCode !== null) {
    // >5000 chars keeps a marker instead of echoing megabytes (§4.4 table row:
    // unsupported_format with text "input_exceeds_limit" — never silent truncation).
    return errorMessage(rawRef, config.provider, badCode, "input_exceeds_limit");
  }

  // 2. Resolve provider at CALL time (env swap needs zero code change).
  const provider = getTtsProvider(config.provider);
  if (!provider) {
    throw new MediaError("unknown_provider", `no TTS provider registered under id "${config.provider}"`);
  }

  // 3. Provider call under the timeout bound; failures rethrow normalized.
  const t0 = Date.now();
  const result = await withTimeout(
    runProvider(provider, input, opts ?? {}),
    config.timeout_ms,
    `tts provider "${config.provider}" timed out after ${config.timeout_ms}ms`,
  );
  return finalize(input, config.provider, result, Date.now() - t0);
}

function runProvider(provider: TtsProvider, input: TtsInput, opts: TtsOptions): Promise<TtsResult> {
  return provider.synthesize(input, opts).catch((err: unknown) => {
    if (err instanceof MediaError) throw err;
    throw new MediaError(
      "provider_error",
      `tts provider "${provider.id}" failed: ${err instanceof Error ? err.message : String(err)}`,
    );
  });
}

//#endregion

//#region synthesizeStream (MED-TTS-01 incremental delivery — DP-C §5.1)

const POLYFILL_SLICE_BYTES = 4096;

/**
 * Stream synthesis incrementally as TtsChunks (MED-TTS-01). Native-streaming
 * providers delegate verbatim; others are polyfilled by synthesizing whole and
 * yielding 4KB base64 slices. Backpressure is inherent: chunks yield only when
 * the consumer asks for the next iteration.
 *
 * - Bad input → THROWS TtsInputError (empty_input|unsupported_format) before
 *   the first yield (streams have no envelope channel; use synthesize()).
 * - opts.signal checked before every yield AND before the provider fetch;
 *   abort throws DOMException("Aborted","AbortError"). Callers map it to a
 *   final error:"tts_interrupted" envelope (§5.2 — see ./tts/README.md).
 */
export async function* synthesizeStream(input: TtsInput, opts?: TtsOptions): AsyncIterable<TtsChunk> {
  const config = loadMediaConfig("tts", opts ?? null);
  const signal = opts?.signal;

  // Validation before the first yield (§4.4 table — same codes as synthesize).
  const badCode = validateTtsInput(input, opts);
  if (badCode === "empty_input") throw new TtsInputError("empty_input");
  if (badCode !== null) throw new TtsInputError(badCode, "input_exceeds_limit");

  // Cancellation check before the provider byte fetch (§5.2 semantics).
  if (signal?.aborted) throw new DOMException("Aborted", "AbortError");

  const provider = getTtsProvider(config.provider);
  if (!provider) {
    throw new MediaError("unknown_provider", `no TTS provider registered under id "${config.provider}"`);
  }

  const t0 = Date.now();
  if (provider.synthesizeStream) {
    // Native path: delegate; re-check abort before EVERY yield (§5.2).
    for await (const chunk of provider.synthesizeStream(input, opts ?? {})) {
      if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
      yield chunk;
    }
    return;
  }

  // Polyfill (request/response providers): synthesize whole, slice to 4KB.
  const { audio } = await runProvider(provider, input, opts ?? {});
  let index = 0;
  for (let i = 0; i < audio.length; i += POLYFILL_SLICE_BYTES, index++) {
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
    yield {
      audio_chunk: Buffer.from(audio.slice(i, i + POLYFILL_SLICE_BYTES)).toString("base64"),
      delta_text: "", // not available in polyfill; native providers fill this
      index,
      is_final: i + POLYFILL_SLICE_BYTES >= audio.length,
      ...(i === 0 ? { latency_ms: Date.now() - t0 } : {}),
    };
  }
}

//#endregion

//#region Timeout bound (never silent hang, §7.2)

async function withTimeout<T>(p: Promise<T>, ms: number, label: string): Promise<T> {
  let timer: NodeJS.Timeout | undefined;
  const timeout = new Promise<never>((_, reject) => {
    timer = setTimeout(() => reject(new MediaError("provider_error", label)), ms);
  });
  try {
    return await Promise.race([p, timeout]);
  } finally {
    clearTimeout(timer);
  }
}

//#endregion
