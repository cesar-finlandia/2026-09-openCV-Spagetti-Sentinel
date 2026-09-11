// Requirement IDs: MED-01, MED-02, MED-03, MED-04, MED-REU-01, MED-REU-02,
// MED-RES-01, MED-RES-02, RES-REU-02, GOV-RES-01, GOV-RES-04, XCUT-08
// PDF public entrypoint — DP-C §4.3 (text extraction with OCR fallback).
//
// extract(input, opts?) implements the §4.3 algorithm EXACTLY:
//   1. PdfTextProvider.extractText(input)          — text layer first
//   2. per page trimmed length < ocrThresholdChars — OCR step when available,
//      else keep short text with ocr_used:false and LOWERED confidence
//   3. concatenate page texts → result.text
//   4. confidence = weighted mean of page confidences (OCR pages lower)
//   5. structured_fields {page_count, extraction_mode, pages[], ocr_provider}
//
// §7.2 error contract: bad-input codes (empty_input | corrupt_file |
// unsupported_format) are RETURNED as UnifiedMediaMessage.error with NO
// provider call; parse-shaped provider failures are mapped to corrupt_file;
// every other provider failure THROWS normalized MediaError so RES-01 can
// retry/fallback (MED-RES-01). Every path is bounded by timeout_ms
// (default 15000) — never silent hang. OCR-binary-missing degrades
// gracefully (GOV-RES-04): text-layer result, ocr_provider:"none", no throw.
//
// Isolation (MED-REU-02 / DP-C §8.1): imports ONLY media-message types, media
// config, its own pdf/providers/* and pdf/ocr/* — NEVER stt/vision/tts.

import { readFileSync } from "node:fs";
import { loadMediaConfig, MediaError } from "./config.js";
import type { ResolvedMediaConfig } from "./config.js";
import type { UnifiedMediaMessage } from "./media-message.js";
import {
  getPdfTextProvider,
  getOcrProvider,
  registerPdfTextProvider,
  registerOcrProvider,
  PdfParseError,
} from "./pdf/providers/types.js";
import type {
  OcrProvider,
  PdfInput,
  PdfOptions,
  PdfTextResult,
} from "./pdf/providers/types.js";
import * as pdfSyntheticFixture from "./pdf/providers/synthetic-fixture.js";
import * as pdfjsProvider from "./pdf/providers/pdfjs.js";
import * as ocrTesseract from "./pdf/ocr/tesseract.js";
import * as ocrNone from "./pdf/ocr/none.js";
import * as ocrSyntheticFixture from "./pdf/ocr/synthetic-fixture.js";

export type { PdfInput, PdfOptions } from "./pdf/providers/types.js";

//#region Built-in registration (DP-C §4.3 — synthetic-fixture ALWAYS available)

pdfSyntheticFixture.register();
pdfjsProvider.register();
ocrTesseract.register();
ocrNone.register();
ocrSyntheticFixture.register();

/** Register an additional TEXT provider at runtime (Engine-supplied backends). */
export function addPdfTextProvider(p: Parameters<typeof registerPdfTextProvider>[0]): void {
  registerPdfTextProvider(p);
}

/** Register an additional OCR provider at runtime (Engine-supplied backends). */
export function addOcrProvider(p: Parameters<typeof registerOcrProvider>[0]): void {
  registerOcrProvider(p);
}

//#endregion

//#region Input validation (MED-RES-02 / DP-C §4.3 failure table)

const DEFAULT_OCR_THRESHOLD_CHARS = 40;

function bytesOf(input: PdfInput): Uint8Array {
  if ("buffer" in input) return input.buffer;
  if ("base64" in input) return new Uint8Array(Buffer.from(input.base64, "base64"));
  return new Uint8Array(readFileSync(input.path));
}

function rawRefOf(input: PdfInput): string {
  if ("path" in input) return input.path;
  if ("buffer" in input) return `buffer:${input.buffer.byteLength}b`;
  return "base64:inline";
}

function extensionOf(input: PdfInput): string {
  if (!("path" in input)) return "pdf";
  const ext = input.path.split(/[\\/]/).pop()?.split(".").pop() ?? "";
  return ext.toLowerCase();
}

/**
 * Validate one materialized PDF buffer per the §4.3 failure table:
 * zero bytes → empty_input; non-.pdf document (e.g. .docx) →
 * unsupported_format; bad/missing %PDF header → corrupt_file.
 * Returns null when OK.
 */
export function validatePdfBuffer(input: PdfInput, bytes: Uint8Array): UnifiedMediaMessage["error"] {
  if (bytes.byteLength === 0) return "empty_input";
  const ext = extensionOf(input);
  if (ext !== "" && ext !== "pdf") return "unsupported_format";
  if (Buffer.from(bytes.subarray(0, 5)).toString("latin1") !== "%PDF-") return "corrupt_file";
  return null;
}

//#endregion

//#region OCR provider resolution (§4.3 two-layer pairing)

/**
 * Resolve the OCR engine for this call. Fixture note (DP-C §4.3): when the
 * text layer is the checked-in synthetic fixture, the OCR step is served by
 * the synthetic-fixture OCR provider — extract.json text, NO binary needed
 * for offline CI. Otherwise the configured id (default tesseract per
 * config/media.json) is resolved and availability-probed; a missing binary →
 * null so the caller degrades gracefully (GOV-RES-04), never throws.
 */
function resolveOcrProvider(
  config: ResolvedMediaConfig,
  opts: PdfOptions,
  textProviderId: string,
): OcrProvider | null {
  const requested = (opts.ocr_provider ?? config.ocr_provider ?? "none") || "none";
  if (requested === "none") return null;
  // Offline fixture pairing — deterministic MED-AC-01 OCR fallback path.
  if (textProviderId === "synthetic-fixture" && requested === "tesseract") {
    const synthetic = getOcrProvider("synthetic-fixture");
    if (synthetic?.available()) return synthetic;
  }
  const provider = getOcrProvider(requested);
  if (!provider || !provider.available()) return null; // graceful degrade
  return provider;
}

//#endregion

//#region extract (async main path, §4.3 algorithm steps 1–5)

interface ExtractedPage {
  page: number;
  text: string;
  ocr_used: boolean;
  confidence: number;
}

/**
 * Extract a PDF into a UnifiedMediaMessage (type:"pdf"). See module header
 * for the exact §4.3 algorithm and error contract.
 */
export async function extract(input: PdfInput, opts?: PdfOptions): Promise<UnifiedMediaMessage> {
  const config = loadMediaConfig("pdf", opts ?? null);
  const timeoutMs = config.timeout_ms;
  const rawRef = rawRefOf(input);

  const badCode = await withTimeout(
    validateInput(input),
    timeoutMs,
    `pdf input could not be read within ${timeoutMs}ms`,
  );
  if (badCode) {
    return errorMessage(rawRef, config.provider, badCode);
  }

  const threshold = opts?.ocrThresholdChars ?? DEFAULT_OCR_THRESHOLD_CHARS;

  try {
    return await withTimeout(
      runPipeline(input, opts ?? {}, config, rawRef, threshold),
      timeoutMs,
      `pdf extraction timed out after ${timeoutMs}ms`,
    );
  } catch (err) {
    // §4.3 failure table: parse-shaped provider errors map to corrupt_file;
    // everything else rethrows normalized for RES-01 (MED-RES-01).
    if (err instanceof PdfParseError) {
      return errorMessage(rawRef, config.provider, "corrupt_file");
    }
    throw err;
  }
}

/** Read bytes for validation; unreadable paths surface as typed errors.
 * Extension check comes FIRST so unsupported formats never touch disk. */
async function validateInput(input: PdfInput): Promise<UnifiedMediaMessage["error"]> {
  const ext = extensionOf(input);
  if (ext !== "" && ext !== "pdf") return "unsupported_format";
  let bytes: Uint8Array;
  try {
    bytes = bytesOf(input);
  } catch (err) {
    throw new MediaError(
      "provider_error",
      `pdf input could not be read: ${err instanceof Error ? err.message : String(err)}`,
    );
  }
  return validatePdfBuffer(input, bytes);
}

async function runPipeline(
  input: PdfInput,
  opts: PdfOptions,
  config: ResolvedMediaConfig,
  rawRef: string,
  threshold: number,
): Promise<UnifiedMediaMessage> {
  // Step 1: text layer first (fast path for born-digital PDFs).
  const textProvider = getPdfTextProvider(config.provider);
  if (!textProvider) {
    throw new MediaError(
      "unknown_provider",
      `no PDF text provider registered under id "${config.provider}"`,
    );
  }
  let textResult: PdfTextResult;
  try {
    textResult = await textProvider.extractText(input);
  } catch (err) {
    if (err instanceof MediaError || err instanceof PdfParseError) throw err;
    throw new MediaError(
      "provider_error",
      `pdf provider "${textProvider.id}" failed: ${err instanceof Error ? err.message : String(err)}`,
    );
  }

  // Step 2: OCR pass on pages below ocrThresholdChars.
  const ocr = resolveOcrProvider(config, opts, textProvider.id);
  const reportedOcrId = ocr ? ocr.id : "none";
  const pages: ExtractedPage[] = [];
  let degradedOcr = false; // tesseract requested but unavailable → GOV-RES-04
  const requestedOcr = (opts.ocr_provider ?? config.ocr_provider ?? "none") || "none";
  if (!ocr && requestedOcr !== "none") degradedOcr = true;

  for (const p of textResult.textByPage) {
    const short = p.text.trim().length < threshold;
    if (short && ocr) {
      try {
        const image = renderPageForOcr(input, p.page);
        const result = await ocr.ocr(image, opts);
        pages.push({
          page: p.page,
          text: result.text,
          ocr_used: true,
          confidence: clamp01(result.confidence),
        });
        continue;
      } catch (err) {
        if (err instanceof MediaError) throw err;
        throw new MediaError(
          "provider_error",
          `pdf ocr provider "${ocr.id}" failed: ${err instanceof Error ? err.message : String(err)}`,
        );
      }
    }
    // No OCR engine (disabled or unavailable) → keep short text with lowered
    // confidence; ocr_used stays false (§4.3 step 2 else-branch).
    pages.push({
      page: p.page,
      text: p.text,
      ocr_used: false,
      confidence: short ? Math.min(clamp01(textResult.confidence), 0.35) : clamp01(textResult.confidence),
    });
  }

  return finalize(input, config.provider, rawRef, pages, reportedOcrId, degradedOcr);
}

/**
 * Render one page to an image for the OCR engine. Rendering is OPTIONAL per
 * DP-C §4.3 ("lightweight, optional"): the synthetic-fixture OCR engine
 * ignores the bytes entirely (fixture note), and binary engines receive the
 * raw document bytes as a best-effort payload. A real canvas renderer can be
 * added later without changing this wrapper's contract.
 */
function renderPageForOcr(input: PdfInput, _page: number): Uint8Array {
  return bytesOf(input);
}

//#endregion

//#region Finalize + bounds (§4.3 steps 3–5, §7.2 never-hang)

function clamp01(v: number): number {
  return Math.min(1, Math.max(0, Number.isFinite(v) ? v : 0));
}

/** Step 5: assemble the UnifiedMediaMessage from per-page results. */
function finalize(
  input: PdfInput,
  providerId: string,
  rawRef: string,
  pages: ExtractedPage[],
  ocrProviderId: string,
  degradedOcr: boolean,
): UnifiedMediaMessage {
  const extractionMode =
    pages.length > 0 && pages.every((p) => p.ocr_used)
      ? "ocr_only"
      : pages.some((p) => p.ocr_used)
        ? "text_then_ocr"
        : "text_only";
  // Step 3: concatenate page texts. Step 4: weighted mean of page confidences
  // (equal weights; OCR pages already carry lower individual confidence).
  const confidence =
    pages.length === 0 ? 0 : pages.reduce((sum, p) => sum + p.confidence, 0) / pages.length;
  return {
    type: "pdf",
    raw_ref: rawRefOf(input),
    text: pages.map((p) => p.text).join("\n"),
    structured_fields: {
      page_count: pages.length,
      extraction_mode: extractionMode,
      pages: pages.map((p) => ({ page: p.page, text: p.text, ocr_used: p.ocr_used, confidence: clamp01(p.confidence) })),
      // §7.2 GOV-RES-04 row: binary missing → reported as "none".
      ocr_provider: degradedOcr ? "none" : ocrProviderId,
      ...(degradedOcr ? { ocr_degraded: true } : {}),
    },
    confidence: clamp01(confidence),
    // MED-04/NONGOAL-06 provenance: true iff produced by the checked-in
    // synthetic fixture provider.
    synthetic: providerId === "synthetic-fixture",
    timestamp: new Date().toISOString(),
    provider: providerId,
    error: null,
    version: "1.0.0",
  };
}

function errorMessage(rawRef: string, providerId: string, code: NonNullable<UnifiedMediaMessage["error"]>): UnifiedMediaMessage {
  return {
    type: "pdf",
    raw_ref: rawRef,
    text: "",
    structured_fields: null,
    confidence: 0,
    synthetic: false,
    timestamp: new Date().toISOString(),
    provider: providerId,
    error: code,
    version: "1.0.0",
  };
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
