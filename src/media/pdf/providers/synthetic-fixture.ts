// Requirement IDs: MED-04, MED-AC-01, GOV-REU-02, GOV-MIN-04, NONGOAL-06
// Always-available offline PDF text provider — DP-C §4.3 built-in.
//
// Reads the checked-in synthetic fixture pair:
//   examples/dummy-fixtures/media/pdf/sample.pdf   (2 pages: born-digital p1,
//    image-only scanned p2)
//   examples/dummy-fixtures/media/pdf/extract.json (expected extraction)
//
// Behavior per §4.3 fixture note: returns REAL text for the born-digital p1
// (from extract.json) and DELIBERATELY SHORT text for the scanned p2 so the
// wrapper's per-page `ocrThresholdChars` check trips and the OCR fallback step
// runs. The paired OCR step in synthetic-fixture mode is served by
// pdf/ocr/synthetic-fixture.* straight from extract.json — NO real OCR binary
// needed for offline CI (GOV-MIN-04 / MED-AC-01).
//
// Fixture content is Acme Corp/widget synthetic only (GOV-REU-02); provenance
// marker `synthetic` is set by the wrapper because this id is
// "synthetic-fixture" (MED-04/NONGOAL-06).

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { PdfParseError, registerPdfTextProvider } from "./types.js";
import type { PdfInput, PdfTextProvider, PdfTextResult } from "./types.js";

/** Marker emitted for image-only pages — intentionally < ocrThresholdChars
 * (default 40) so the wrapper's OCR fallback triggers (§4.3 algorithm step 2). */
export const SCANNED_PAGE_MARKER = "[scanned page]";

interface ExtractFixture {
  page_count: number;
  extraction_mode: string;
  pages: Array<{ page: number; ocr_used: boolean; text: string }>;
  text: string;
}

function repoRoot(): string {
  // src/media/pdf/providers/synthetic-fixture.ts → repo root is ../../../../
  return fileURLToPath(new URL("../../../..", import.meta.url));
}

const EXTRACT_PATH = () =>
  `${repoRoot()}examples/dummy-fixtures/media/pdf/extract.json`;

let cache: ExtractFixture | null = null;

function loadExtract(): ExtractFixture {
  return (cache ??= JSON.parse(readFileSync(EXTRACT_PATH(), "utf8")) as ExtractFixture);
}

/** Touch fixture bytes so a missing/corrupt checked-in file surfaces as a
 * typed parse error instead of silently returning canned text. */
function assertFixturePdf(input: PdfInput): void {
  if (!("path" in input)) return;
  const pdf = readFileSync(input.path);
  if (Buffer.from(pdf.subarray(0, 5)).toString("latin1") !== "%PDF-") {
    throw new PdfParseError(`fixture ${input.path} is not a PDF (%PDF header missing)`);
  }
}

class SyntheticFixturePdfTextProvider implements PdfTextProvider {
  readonly id = "synthetic-fixture";

  async extractText(input: PdfInput): Promise<PdfTextResult> {
    assertFixturePdf(input);
    const fixture = loadExtract();
    const textByPage = fixture.pages.map((p) => ({
      page: p.page,
      // Born-digital page → full expected text; scanned page → short marker
      // that forces the OCR branch of the §4.3 extraction algorithm.
      text: p.ocr_used ? SCANNED_PAGE_MARKER : p.text,
    }));
    return { textByPage, confidence: 0.95 };
  }
}

const INSTANCE = new SyntheticFixturePdfTextProvider();

/** Self-register so getPdfTextProvider("synthetic-fixture") works after import. */
export function register(): void {
  registerPdfTextProvider(INSTANCE);
}
export { INSTANCE as syntheticFixturePdfTextProvider };
