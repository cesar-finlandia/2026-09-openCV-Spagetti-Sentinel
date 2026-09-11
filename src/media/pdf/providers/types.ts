// Requirement IDs: MED-01, MED-03, MED-REU-02, RES-03, GOV-MIN-04, XCUT-08
// PDF provider abstraction + runtime registries — DP-C §4.3.
//
// TWO layered providers are configured independently but invoked by ONE
// wrapper; the OCR fallback lives INSIDE the wrapper (mechanical), not via
// RES-03 secondary-provider fallback (which is whole-wrapper fallback):
//
//   - PdfTextProvider  — text-layer extraction ("pypdf" | "pdfjs" |
//     "synthetic-fixture" | "none")
//   - OcrProvider      — page-image OCR ("tesseract" | "synthetic-fixture"
//     | "none")
//
// Providers register via registerPdfTextProvider()/registerOcrProvider(); the
// wrapper resolves at CALL time so MED_PDF_PROVIDER / MED_OCR_PROVIDER env
// swaps need zero code change (MED-03). A missing text-provider id returns
// null → wrapper throws MediaError("unknown_provider") per DP-C §7.2.
//
// Isolation (MED-REU-02): this file imports nothing outside src/media shared
// surfaces (media-message/config types) — never stt/vision/tts (CI grep
// guard, DP-C §8.1).

import type { MediaConfig } from "../../config.js";

//#region Input/options (DP-C §4.3 PdfInput/PdfOptions)

/** Raw document input variants accepted by extract() — DP-C §4.3 PdfInput.
 * PDF ONLY: other document formats map to `unsupported_format` (scope is PDF
 * per requirement). Exactly one variant key must be present. */
export type PdfInput =
  | { path: string }
  | { buffer: Uint8Array }
  | { base64: string };

/** Per-wrapper options: MediaConfig slice + generic hints only (MED-REU-01 —
 * no persona/domain vocabulary). */
export type PdfOptions = Partial<MediaConfig> & {
  /** Min trimmed chars per page to consider text extraction sufficient
   * (default 40 — pages below this trigger the OCR step). */
  ocrThresholdChars?: number;
  /** Tesseract language hint, e.g. "eng". Generic, not domain-tuned. */
  ocrLanguages?: string;
};

/** One extracted page as returned by a text provider. */
export interface PdfPageText {
  page: number;
  text: string;
}

/** Normalized text-provider result — wrapper runs the OCR pass on top. */
export interface PdfTextResult {
  textByPage: PdfPageText[];
  /** Confidence normalized to 0..1 for the TEXT layer overall. */
  confidence: number;
}

/**
 * One PDF text-layer backend. Implementations MUST throw on failure so
 * RES-01 can retry/fallback (RES-REU-02); parse-shaped failures (truncated
 * xref, bad objects) MUST throw PdfParseError so the wrapper can map them to
 * `error:"corrupt_file"` per the §4.3 failure table instead of a raw stack.
 */
export interface PdfTextProvider {
  /** Lowercase kebab-case id, e.g. "pypdf", "pdfjs", "synthetic-fixture". */
  readonly id: string;
  extractText(pdf: PdfInput): Promise<PdfTextResult>;
}

/** Normalized OCR result for one rendered page image. */
export interface OcrResult {
  text: string;
  /** Confidence normalized to 0..1 (OCR pages carry lower confidence). */
  confidence: number;
}

/**
 * One OCR engine backend (DP-C §4.3 second layer). `available` is checked by
 * the wrapper BEFORE invoking ocr(): when a binary-backed provider is not
 * installed the wrapper degrades gracefully (GOV-RES-04) — text-layer result,
 * structured_fields.ocr_provider:"none", lowered confidence, NO throw.
 */
export interface OcrProvider {
  /** Lowercase kebab-case id, e.g. "tesseract", "synthetic-fixture", "none". */
  readonly id: string;
  /** Whether this engine can actually run in the current environment. */
  available(): boolean;
  /** OCR one rendered page image. Throws MediaError on hard failures. */
  ocr(pageImage: Uint8Array, opts?: PdfOptions): Promise<OcrResult>;
}

//#endregion

//#region Parse-error marker (§4.3 corrupt_file mapping)

/** Thrown by text providers when the byte stream is not a readable PDF (bad
 * header / truncated / broken xref). The wrapper catches this and RETURNS a
 * UnifiedMediaMessage with error:"corrupt_file" — never an uncaught
 * PdfReadError-style stack (MED-RES-02, GOV-RES-01). Any OTHER provider
 * failure is rethrown normalized as MediaError("provider_error") for RES-01. */
export class PdfParseError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "PdfParseError";
  }
}

//#endregion

//#region Runtime registries (DP-C §4.3 provider swap without code change)

const TEXT_REGISTRY = new Map<string, PdfTextProvider>();
const OCR_REGISTRY = new Map<string, OcrProvider>();

/** Register (or replace) a text provider under its own id. Idempotent per id. */
export function registerPdfTextProvider(p: PdfTextProvider): void {
  TEXT_REGISTRY.set(p.id, p);
}

/** Resolve a text provider by id at call time; null when unknown → caller
 * throws MediaError("unknown_provider") (DP-C §7.2 malformed-config row). */
export function getPdfTextProvider(id: string): PdfTextProvider | null {
  return TEXT_REGISTRY.get(id) ?? null;
}

/** All registered text-provider ids (diagnostics/tests only). */
export function listPdfTextProviders(): string[] {
  return [...TEXT_REGISTRY.keys()].sort();
}

/** Register (or replace) an OCR provider under its own id. Idempotent per id. */
export function registerOcrProvider(p: OcrProvider): void {
  OCR_REGISTRY.set(p.id, p);
}

/** Resolve an OCR provider by id at call time; null when unknown → caller
 * throws MediaError("unknown_provider"). */
export function getOcrProvider(id: string): OcrProvider | null {
  return OCR_REGISTRY.get(id) ?? null;
}

/** All registered OCR ids (diagnostics/tests only). */
export function listOcrProviders(): string[] {
  return [...OCR_REGISTRY.keys()].sort();
}

//#endregion
