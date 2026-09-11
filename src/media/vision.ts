// Requirement IDs: MED-01, MED-02, MED-03, MED-04, MED-REU-01, MED-REU-02,
// MED-RES-01, MED-RES-02, RES-REU-02, GOV-RES-01, GOV-RES-04, XCUT-08
// Vision public entrypoint — DP-C §4.2.
//
// caption(input, opts?) normalizes raw image input, applies the §7.2 error
// contract (bad-input codes RETURNED as UnifiedMediaMessage.error; provider
// failures THROWN as MediaError so RES-01 can retry/fallback), resolves the
// provider at call time via getVisionProvider(config.provider) (MED-03 env
// swap, zero code change), resolves the GENERIC prompt (default-prompt.txt ←
// config.vision.prompt/MED_VISION_PROMPT ← opts.prompt — MED-REU-01), and
// bounds every path with timeout_ms (default 15000 — never silent hang).
//
// Isolation (MED-REU-02 / DP-C §8.1): imports ONLY media-message types, media
// config, its own vision/providers/* — NEVER stt/pdf/tts. Closure-friendly for
// RES-01: caller wraps as () => caption(input, opts) (zero required args).

import { readFileSync } from "node:fs";
import { loadMediaConfig, MediaError } from "./config.js";
import type { UnifiedMediaMessage } from "./media-message.js";
import { defaultPrompt, getVisionProvider, registerVisionProvider } from "./vision/providers/types.js";
import type { ImageInput, VisionOptions, VisionProvider, VisionResult } from "./vision/providers/types.js";
import * as syntheticFixture from "./vision/providers/synthetic-fixture.js";
import * as openaiGpt4oVision from "./vision/providers/openai-gpt4o-vision.js";
import * as anthropicClaudeVision from "./vision/providers/anthropic-claude-vision.js";

export type { ImageInput, VisionOptions } from "./vision/providers/types.js";
export { addVisionProvider, defaultPrompt };

//#region Built-in registration (DP-C §4.2 — synthetic-fixture ALWAYS available)

syntheticFixture.register();
openaiGpt4oVision.register();
anthropicClaudeVision.register();

/** Register an additional provider at runtime (Engine-supplied backends). */
function addVisionProvider(p: Parameters<typeof registerVisionProvider>[0]): void {
  registerVisionProvider(p);
}

//#endregion

//#region Input validation helpers (MED-RES-02 / DP-C §7.2 failure table)

const SUPPORTED_FORMATS = new Set(["png", "jpeg", "jpg", "webp"]);
/** PNG signature(8) + mandatory IHDR(25) minimum. */
const PNG_MIN_BYTES = 33;

function extFormatOf(path: string): string {
  const ext = path.split(".").pop() ?? "";
  return ext.toLowerCase();
}

/** Format DECLARED by the input: explicit mime wins, else path extension. */
function declaredFormatOf(input: ImageInput): string | undefined {
  if ("base64" in input) return extFormatOf(String(input.mime ?? "").split("/").pop() ?? "");
  if ("buffer" in input && input.mime) return extFormatOf(String(input.mime).split("/").pop() ?? "");
  if ("path" in input) return extFormatOf(input.path);
  return undefined;
}

/** Format SNIFFED from magic bytes: png | jpeg | webp | null (unknown). */
function sniffFormat(bytes: Uint8Array): string | null {
  if (
    bytes.byteLength >= 8 &&
    bytes[0] === 0x89 && bytes[1] === 0x50 && bytes[2] === 0x4e && bytes[3] === 0x47 &&
    bytes[4] === 0x0d && bytes[5] === 0x0a && bytes[6] === 0x1a && bytes[7] === 0x0a
  ) {
    return "png";
  }
  if (bytes.byteLength >= 3 && bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff) {
    return "jpeg";
  }
  if (
    bytes.byteLength >= 12 &&
    bytes[0] === 0x52 && bytes[1] === 0x49 && bytes[2] === 0x46 && bytes[3] === 0x46 &&
    bytes[8] === 0x57 && bytes[9] === 0x45 && bytes[10] === 0x42 && bytes[11] === 0x50
  ) {
    return "webp";
  }
  return null;
}

function hasPngIendTrailer(bytes: Uint8Array): boolean {
  // Final chunk is always the 12-byte IEND chunk: len=0 + "IEND" + CRC.
  const n = bytes.byteLength;
  return (
    n >= PNG_MIN_BYTES &&
    bytes[n - 12] === 0 && bytes[n - 11] === 0 && bytes[n - 10] === 0 && bytes[n - 9] === 0 &&
    bytes[n - 8] === 0x49 && bytes[n - 7] === 0x45 && bytes[n - 6] === 0x4e && bytes[n - 5] === 0x44
  );
}

function hasJpegEoiTrailer(bytes: Uint8Array): boolean {
  const n = bytes.byteLength;
  return n >= 4 && bytes[n - 2] === 0xff && bytes[n - 1] === 0xd9;
}

/**
 * Validate one materialized image buffer per the §4.2 failure table:
 * zero bytes → empty_input; unsupported declared format (e.g. image/tiff) →
 * unsupported_format; unknown magic / truncated PNG-JPEG trailers →
 * corrupt_file. Returns null when OK.
 */
export function validateImageBuffer(input: ImageInput, bytes: Uint8Array): UnifiedMediaMessage["error"] {
  if (bytes.byteLength === 0) return "empty_input";
  const declared = declaredFormatOf(input);
  if (declared !== undefined && declared !== "" && !SUPPORTED_FORMATS.has(declared)) {
    return "unsupported_format";
  }
  const sniffed = sniffFormat(bytes);
  if (sniffed === null) return "corrupt_file";
  if (declared !== undefined && declared !== "" && declared !== sniffed && !(declared === "jpg" && sniffed === "jpeg")) {
    return "corrupt_file"; // declared type contradicts actual bytes
  }
  const complete =
    sniffed === "png"
      ? hasPngIendTrailer(bytes)
      : sniffed === "jpeg"
        ? hasJpegEoiTrailer(bytes)
        : true; // webp completeness = RIFF/WEBP header already checked
  return complete ? null : "corrupt_file";
}

/** Pixel dimensions when cheaply parseable: PNG IHDR / JPEG SOF markers;
 * null otherwise (providers may still report their own dimensions). */
function imageDimensions(bytes: Uint8Array): { width: number; height: number } | null {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  if (sniffFormat(bytes) === "png" && bytes.byteLength >= 24) {
    return { width: view.getUint32(16), height: view.getUint32(20) };
  }
  if (sniffFormat(bytes) !== "jpeg") return null;
  // Walk JPEG segments for an SOF0..SOF3 frame header.
  let off = 2;
  while (off + 9 < bytes.byteLength) {
    const markerByte = bytes[off + 1];
    if (bytes[off] !== 0xff || markerByte === undefined) break;
    const marker = markerByte;
    const len = view.getUint16(off + 2);
    if (marker >= 0xc0 && marker <= 0xc3) {
      return { height: view.getUint16(off + 5), width: view.getUint16(off + 7) };
    }
    off += 2 + len;
  }
  return null;
}

function bytesOf(input: ImageInput): Uint8Array {
  if ("buffer" in input) return input.buffer;
  if ("base64" in input) return Buffer.from(input.base64, "base64");
  if ("path" in input) return readFileSync(input.path);
  throw new Error("bytesOf: url inputs are fetched by caption()");
}

function rawRefOf(input: ImageInput): string {
  if ("path" in input) return input.path;
  if ("buffer" in input) return `buffer:${input.buffer.byteLength}b`;
  if ("base64" in input) return "base64:inline";
  return `url:${input.url}`;
}

//#endregion

//#region caption (async main path)

function errorMessage(input: ImageInput, provider: string, code: NonNullable<UnifiedMediaMessage["error"]>): UnifiedMediaMessage {
  return {
    type: "vision",
    raw_ref: rawRefOf(input),
    text: "",
    structured_fields: null,
    confidence: 0,
    synthetic: false,
    timestamp: new Date().toISOString(),
    provider,
    error: code,
    version: "1.0.0",
  };
}

/** Generic-prompt resolution (MED-REU-01 / DP-C §6.2): per-call opts.prompt
 * overrides config.prompt (which carries MED_VISION_PROMPT); null → checked-in
 * default-prompt.txt. Domain/persona prompts are forbidden by CI grep guard. */
export function resolvePrompt(opts?: VisionOptions | null, configPrompt?: string | null): string {
  const fromCall = opts?.prompt?.trim();
  if (fromCall) return fromCall;
  const fromConfig = configPrompt?.trim();
  if (fromConfig) return fromConfig;
  return defaultPrompt();
}

/**
 * Caption one image into a UnifiedMediaMessage (type:"vision").
 *
 * - Bad input → RESOLVED message with error empty_input|corrupt_file|
 *   unsupported_format (offline url), confidence 0, no provider call (§7.2).
 * - Unknown provider id → THROWS MediaError("unknown_provider") (§7.2).
 * - Provider/network failure → THROWS normalized MediaError("provider_error")
 *   so RES-01 can retry/fallback (MED-RES-01); never swallowed into .error.
 * - Every path bounded by timeout_ms (default 15000).
 */
export async function caption(input: ImageInput, opts?: VisionOptions): Promise<UnifiedMediaMessage> {
  const config = loadMediaConfig("vision", opts ?? null);
  const timeoutMs = config.timeout_ms;

  // 1. Materialize + validate input BEFORE any provider work (no provider call
  //    on bad input per §4.2 failure table). url inputs are fetched here under
  //    the same timeout bound; NETWORK=disabled → unsupported_format.
  let bytes: Uint8Array;
  try {
    bytes = "url" in input ? await fetchUrlImage(input.url, timeoutMs) : bytesOf(input);
  } catch (err) {
    if (err instanceof OfflineUrlError) {
      return errorMessage(input, config.provider, "unsupported_format");
    }
    throw new MediaError(
      "provider_error",
      `vision input could not be read: ${err instanceof Error ? err.message : String(err)}`,
    );
  }
  const badCode = validateImageBuffer(input, bytes);
  if (badCode) return errorMessage(input, config.provider, badCode);
  const dimensions = imageDimensions(bytes);

  // 2. Resolve provider at CALL time (env swap needs zero code change).
  const provider = getVisionProvider(config.provider);
  if (!provider) {
    throw new MediaError(
      "unknown_provider",
      `no vision provider registered under id "${config.provider}"`,
    );
  }

  // 3. Provider call under the timeout bound; failures rethrow normalized.
  const effectiveOpts: VisionOptions = { ...(opts ?? {}), prompt: resolvePrompt(opts, config.prompt) };
  const result = await withTimeout(
    runProvider(provider, input, effectiveOpts),
    timeoutMs,
    `vision provider "${config.provider}" timed out after ${timeoutMs}ms`,
  );

  return finalize(input, config.provider, result, dimensions, effectiveOpts.prompt ?? "");
}

async function fetchUrlImage(url: string, timeoutMs: number): Promise<Uint8Array> {
  // url fetch is OPTIONAL and disabled in offline mode (DP-C §4.2) — reported
  // as unsupported_format, not a crash or hang.
  if (process.env.NETWORK === "disabled") {
    throw new OfflineUrlError(`offline mode: url inputs are disabled (${url})`);
  }
  const res = await withTimeout(fetch(url), timeoutMs, `vision url fetch timed out after ${timeoutMs}ms`);
  if (!res.ok) {
    throw new MediaError("provider_error", `vision url fetch failed with HTTP ${res.status}`);
  }
  return new Uint8Array(await res.arrayBuffer());
}

function runProvider(provider: VisionProvider, input: ImageInput, opts: VisionOptions): Promise<VisionResult> {
  return provider.caption(input, opts).catch((err: unknown) => {
    if (err instanceof MediaError) throw err;
    throw new MediaError(
      "provider_error",
      `vision provider "${provider.id}" failed: ${err instanceof Error ? err.message : String(err)}`,
    );
  });
}

function finalize(
  input: ImageInput,
  providerId: string,
  result: VisionResult,
  dimensions: { width: number; height: number } | null,
  promptUsed: string,
): UnifiedMediaMessage {
  const structured = (result.structured ?? {}) as Record<string, unknown>;
  const providerDimensions = structured.dimensions;
  return {
    type: "vision",
    raw_ref: rawRefOf(input),
    text: result.text,
    structured_fields: {
      objects: Array.isArray(structured.objects) ? structured.objects : [],
      dimensions:
        providerDimensions && typeof providerDimensions === "object" ? providerDimensions : dimensions,
      prompt_used: typeof structured.prompt_used === "string" ? structured.prompt_used : promptUsed,
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

//#region Timeout bounds (never silent hang, §7.2)

/** Sentinel for url inputs rejected because url fetching is disabled offline
 * (§4.2) — mapped to the typed unsupported_format message by caption(). */
class OfflineUrlError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "OfflineUrlError";
  }
}

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
