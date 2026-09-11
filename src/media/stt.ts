// Requirement IDs: MED-01, MED-02, MED-03, MED-04, MED-REU-01, MED-REU-02,
// MED-RES-01, MED-RES-02, RES-REU-02, GOV-RES-01, GOV-RES-04, XCUT-08
// STT public entrypoint — DP-C §4.1.
//
// transcribe(input, opts?) normalizes raw audio input, applies the §7.2 error
// contract (bad-input codes RETURNED as UnifiedMediaMessage.error; provider
// failures THROWN as MediaError so RES-01 can retry/fallback), resolves the
// provider at call time via getSttProvider(config.provider) (MED-03 env swap,
// zero code change), and bounds every path with timeout_ms (default 15000 —
// never silent hang).
//
// Isolation (MED-REU-02 / DP-C §8.1): imports ONLY media-message types, media
// config, its own stt/providers/* — NEVER vision/pdf/tts. Closure-friendly for
// RES-01: caller wraps as () => transcribe(input, opts) (zero required args).

import { loadMediaConfig, MediaError } from "./config.js";
import { readFileSync } from "node:fs";
import type { UnifiedMediaMessage } from "./media-message.js";
import { getSttProvider, registerSttProvider } from "./stt/providers/types.js";
import type { AudioInput, SttOptions, SttResult } from "./stt/providers/types.js";
import * as syntheticFixture from "./stt/providers/synthetic-fixture.js";
import * as openaiWhisper from "./stt/providers/openai-whisper.js";
import * as deepgram from "./stt/providers/deepgram.js";

export type { AudioInput, SttOptions } from "./stt/providers/types.js";

//#region Built-in registration (DP-C §4.1 — synthetic-fixture ALWAYS available)

syntheticFixture.register();
openaiWhisper.register();
deepgram.register();

/** Register an additional provider at runtime (Engine-supplied backends). */
export function addSttProvider(p: Parameters<typeof registerSttProvider>[0]): void {
  registerSttProvider(p);
}

//#endregion

//#region Input validation helpers (MED-RES-02 / DP-C §7.2)

const SUPPORTED_ENCODINGS = new Set(["wav", "wave", "mp3", "webm", "ogg"]);
/** WAV RIFF header is 12 bytes; a usable fmt+data header needs ≥ 44. */
const WAV_MIN_BYTES = 44;

function encodingOf(input: AudioInput): string | undefined {
  if ("encoding" in input && input.encoding) return String(input.encoding).toLowerCase();
  if ("path" in input) {
    const ext = input.path.split(".").pop() ?? "";
    return ext ? ext.toLowerCase() : undefined;
  }
  return undefined;
}

function bytesOf(input: AudioInput): Uint8Array {
  if ("buffer" in input) return input.buffer;
  if ("base64" in input) return Buffer.from(input.base64, "base64");
  if ("path" in input) return readFileSync(input.path);
  throw new Error("bytesOf: stream inputs are collected by the caller");
}

function rawRefOf(input: AudioInput): string {
  if ("path" in input) return input.path;
  if ("buffer" in input) return `buffer:${input.buffer.byteLength}b`;
  if ("base64" in input) return "base64:inline";
  return "stream:inline";
}

/**
 * Validate one materialized audio buffer per the §4.1 failure table:
 * zero bytes → empty_input; bad/truncated RIFF/WAVE header → corrupt_file;
 * explicitly unsupported encoding → unsupported_format. Returns null when OK.
 */
export function validateAudioBuffer(input: AudioInput, bytes: Uint8Array): UnifiedMediaMessage["error"] {
  if (bytes.byteLength === 0) return "empty_input";
  const enc = encodingOf(input);
  if (enc !== undefined && !SUPPORTED_ENCODINGS.has(enc)) return "unsupported_format";
  // Header sniff: anything claiming to be RIFF (explicitly via encoding, path
  // extension, or magic bytes) must carry a usable WAVE header ≥ 44 bytes.
  const startsRiff =
    bytes.byteLength >= 4 &&
    bytes[0] === 0x52 && bytes[1] === 0x49 && bytes[2] === 0x46 && bytes[3] === 0x46;
  const completeWavHeader =
    startsRiff &&
    bytes.byteLength >= WAV_MIN_BYTES &&
    bytes[8] === 0x57 && bytes[9] === 0x41 && bytes[10] === 0x56 && bytes[11] === 0x45;
  const claimsWav = enc === "wav" || enc === "wave" || startsRiff;
  if (claimsWav && !completeWavHeader) return "corrupt_file";
  return null;
}

//#endregion

//#region transcribe (async main path)

/**
 * Transcribe audio to a UnifiedMediaMessage (type:"stt").
 *
 * - Bad input → RESOLVED message with error empty_input|corrupt_file|
 *   unsupported_format, confidence 0, no provider call (MED-RES-02).
 * - Unknown provider id → THROWS MediaError("unknown_provider") (§7.2).
 * - Provider/network failure → THROWS normalized MediaError("provider_error")
 *   so RES-01 can retry/fallback (MED-RES-01); never swallowed into .error.
 * - Every path bounded by timeout_ms (default 15000).
 */
export async function transcribe(input: AudioInput, opts?: SttOptions): Promise<UnifiedMediaMessage> {
  const config = loadMediaConfig("stt", opts ?? null);
  const timeoutMs = config.timeout_ms;

  // 1. Materialize + validate input BEFORE any provider work (no provider call
  //    on bad input per §4.1 failure table). Stream inputs are collected here
  //    under the same timeout bound.
  let bytes: Uint8Array;
  try {
    bytes = "stream" in input ? await collectStream(input.stream, timeoutMs) : bytesOf(input);
  } catch (err) {
    if (err instanceof MediaError) throw err;
    throw new MediaError(
      "provider_error",
      `stt input could not be read: ${err instanceof Error ? err.message : String(err)}`,
    );
  }
  const badCode = validateAudioBuffer(input, bytes);
  if (badCode) {
    return {
      type: "stt",
      raw_ref: rawRefOf(input),
      text: "",
      structured_fields: null,
      confidence: 0,
      synthetic: false,
      timestamp: new Date().toISOString(),
      provider: config.provider,
      error: badCode,
      version: "1.0.0",
    };
  }

  // 2. Resolve provider at CALL time (env swap needs zero code change).
  const provider = getSttProvider(config.provider);
  if (!provider) {
    throw new MediaError(
      "unknown_provider",
      `no STT provider registered under id "${config.provider}"`,
    );
  }

  // 3. Provider call under the timeout bound; failures rethrow normalized.
  const result = await withTimeout(
    runProvider(provider, input, opts ?? {}),
    timeoutMs,
    `stt provider "${config.provider}" timed out after ${timeoutMs}ms`,
  );

  return finalize(input, config.provider, result);
}

function runProvider(
  provider: NonNullable<ReturnType<typeof getSttProvider>>,
  input: AudioInput,
  opts: SttOptions,
): Promise<SttResult> {
  return provider.transcribe(input, opts).catch((err: unknown) => {
    if (err instanceof MediaError) throw err;
    throw new MediaError(
      "provider_error",
      `stt provider "${provider.id}" failed: ${err instanceof Error ? err.message : String(err)}`,
    );
  });
}

function finalize(input: AudioInput, providerId: string, result: SttResult): UnifiedMediaMessage {
  const structured = (result.structured ?? {}) as Record<string, unknown>;
  return {
    type: "stt",
    raw_ref: rawRefOf(input),
    text: result.text,
    structured_fields: {
      language: structured.language ?? null,
      duration_ms: structured.duration_ms ?? null,
      words: Array.isArray(structured.words) ? structured.words : [],
    },
    confidence: Math.min(1, Math.max(0, result.confidence)),
    // MED-04/NONGOAL-06 provenance: true iff produced by the checked-in
    // synthetic fixture provider.
    synthetic: providerId === "synthetic-fixture",
    timestamp: new Date().toISOString(),
    provider: providerId,
    error: null,
    version: "1.0.0",
  };
}

//#endregion

//#region Timeout + stream collection bounds (never silent hang, §7.2)

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

function collectStream(stream: NodeJS.ReadableStream, timeoutMs: number): Promise<Uint8Array> {
  return new Promise<Uint8Array>((resolve, reject) => {
    const chunks: Buffer[] = [];
    let done = false;
    const timer = setTimeout(() => finish(new MediaError("provider_error", "stt stream read timed out")), timeoutMs);
    function finish(err?: Error, data?: Uint8Array): void {
      if (done) return;
      done = true;
      clearTimeout(timer);
      stream.removeListener("data", onData);
      stream.removeListener("end", onEnd);
      stream.removeListener("error", onError);
      if (err) reject(err);
      else resolve(data!);
    }
    function onData(c: Buffer | string): void {
      chunks.push(typeof c === "string" ? Buffer.from(c) : Buffer.from(c));
    }
    function onEnd(): void {
      finish(undefined, Buffer.concat(chunks));
    }
    function onError(err: Error): void {
      // Unreadable input data maps to the corrupt_file family at the wrapper
      // level only after collection; here it surfaces as a read failure which
      // transcribe() reports via validateAudioBuffer on empty/partial data or
      // throws as provider_error for hard stream faults.
      finish(new MediaError("provider_error", `stream read failed: ${err.message}`));
    }
    stream.on("data", onData);
    stream.on("end", onEnd);
    stream.on("error", onError);
  });
}

//#endregion

//#region transcribeSync (synthetic-fixture path ONLY — DP-C §4.1 optional)

/** Synchronous twin restricted to the offline synthetic fixture provider —
 * used by tests/tools that cannot await. Any other provider id throws
 * MediaError("unknown_provider"). */
export function transcribeSync(input: AudioInput, opts?: SttOptions): UnifiedMediaMessage {
  const config = loadMediaConfig("stt", opts ?? null);
  if ("stream" in input) {
    throw new MediaError("provider_error", "transcribeSync does not accept stream inputs");
  }
  const bytes = bytesOf(input);
  const badCode = validateAudioBuffer(input, bytes);
  if (badCode) {
    return {
      type: "stt",
      raw_ref: rawRefOf(input),
      text: "",
      structured_fields: null,
      confidence: 0,
      synthetic: false,
      timestamp: new Date().toISOString(),
      provider: config.provider,
      error: badCode,
      version: "1.0.0",
    };
  }
  const provider = getSttProvider(config.provider);
  if (!provider || config.provider !== "synthetic-fixture") {
    throw new MediaError(
      "unknown_provider",
      `transcribeSync supports only provider "synthetic-fixture" (got "${config.provider}")`,
    );
  }
  const impl = provider as typeof provider & { transcribeSync?: (i: AudioInput) => SttResult };
  if (typeof impl.transcribeSync !== "function") {
    throw new MediaError("provider_error", "synthetic-fixture provider lacks transcribeSync");
  }
  return finalize(input, config.provider, impl.transcribeSync(input));
}

//#endregion
