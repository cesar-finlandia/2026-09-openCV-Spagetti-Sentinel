// Requirement IDs: MED-03, MED-RES-01, MED-RES-02, GOV-MIN-04, GOV-RES-01, XCUT-08
// pdfjs PDF text provider — DP-C §4.3 built-in (Node default per §10.1).
//
// Optional-dep style (GOV-MIN-04): `pdfjs-dist` is required LAZILY on first
// call; an absent SDK surfaces as a THROWN MediaError at call time so RES-01
// can retry/fallback — never a startup crash. Parse-shaped SDK failures
// (PasswordException, InvalidPDFException, missing header) are normalized to
// PdfParseError so the wrapper maps them to error:"corrupt_file" (§4.3
// failure table — never an uncaught PdfReadError-style stack).

import { readFileSync } from "node:fs";
import { MediaError } from "../../config.js";
import { PdfParseError, registerPdfTextProvider } from "./types.js";
import type { PdfInput, PdfTextProvider, PdfTextResult } from "./types.js";

/** Structural surface of the lazily-imported pdfjs document handle we use. */
interface PdfjsDocumentLike {
  numPages: number;
  getPage(n: number): Promise<{
    getTextContent(): Promise<{ items: Array<{ str?: string }> }>;
  }>;
}

interface PdfjsModuleLike {
  getDocument(args: Record<string, unknown>): { promise: Promise<PdfjsDocumentLike> };
}

let pdfjsModuleCache: PdfjsModuleLike | null = null;

function requirePdfjs(): PdfjsModuleLike {
  if (pdfjsModuleCache !== null) return pdfjsModuleCache;
  try {
    // Optional peer dependency — loaded only when this provider is selected.
    // The legacy build is the Node-compatible entrypoint of pdfjs-dist.
    const { createRequire } = require("node:module");
    const req = createRequire(import.meta.url);
    pdfjsModuleCache = req("pdfjs-dist/legacy/build/pdf.mjs") as PdfjsModuleLike;
    return pdfjsModuleCache;
  } catch (err) {
    throw new MediaError(
      "provider_error",
      `pdfjs-dist unavailable for provider pdfjs (${err instanceof Error ? err.message : String(err)})`,
    );
  }
}

function materializeBytes(input: PdfInput): Uint8Array {
  if ("buffer" in input) return input.buffer;
  if ("base64" in input) return new Uint8Array(Buffer.from(input.base64, "base64"));
  return new Uint8Array(readFileSync(input.path));
}

function isParseError(err: unknown): boolean {
  const name = err instanceof Error ? err.name : "";
  return (
    name === "InvalidPDFException" ||
    name === "PasswordException" ||
    name === "MissingPDFException" ||
    name === "UnexpectedResponseException"
  );
}

class PdfjsTextProvider implements PdfTextProvider {
  readonly id = "pdfjs";

  async extractText(input: PdfInput): Promise<PdfTextResult> {
    let doc: PdfjsDocumentLike;
    try {
      const pdfjs = requirePdfjs();
      const data = materializeBytes(input);
      doc = await pdfjs.getDocument({ data, useSystemFonts: true }).promise;
    } catch (err) {
      if (err instanceof MediaError) throw err;
      if (isParseError(err)) {
        throw new PdfParseError(
          `pdfjs could not parse document: ${err instanceof Error ? err.message : String(err)}`,
        );
      }
      throw new MediaError(
        "provider_error",
        `pdfjs provider failed: ${err instanceof Error ? err.message : String(err)}`,
      );
    }

    try {
      const textByPage: Array<{ page: number; text: string }> = [];
      for (let n = 1; n <= doc.numPages; n++) {
        const page = await doc.getPage(n);
        const content = await page.getTextContent();
        const text = content.items
          .map((item) => (typeof item.str === "string" ? item.str : ""))
          .join(" ")
          .replace(/\s+/g, " ")
          .trim();
        textByPage.push({ page: n, text });
      }
      return { textByPage, confidence: 0.9 };
    } catch (err) {
      if (isParseError(err)) {
        throw new PdfParseError(
          `pdfjs page walk failed: ${err instanceof Error ? err.message : String(err)}`,
        );
      }
      throw new MediaError(
        "provider_error",
        `pdfjs provider failed: ${err instanceof Error ? err.message : String(err)}`,
      );
    }
  }
}

const INSTANCE = new PdfjsTextProvider();

/** Self-register so getPdfTextProvider("pdfjs") works after import. */
export function register(): void {
  registerPdfTextProvider(INSTANCE);
}
export { INSTANCE as pdfjsTextProvider };
