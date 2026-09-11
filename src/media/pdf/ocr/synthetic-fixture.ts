// Requirement IDs: MED-04, MED-AC-01, GOV-REU-02, GOV-MIN-04, NONGOAL-06
// Always-available offline OCR provider — DP-C §4.3 fixture note.
//
// Paired automatically with the synthetic-fixture TEXT provider by the
// wrapper: when the text layer is the checked-in fixture, the OCR fallback
// step "just returns extract.json OCR text — no real OCR binary needed for
// offline CI" (DP-C §4.3). Serves page 2's expected OCR text from:
//   examples/dummy-fixtures/media/pdf/extract.json
// Fixture content is Acme Corp/widget synthetic only (GOV-REU-02).

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { registerOcrProvider } from "../providers/types.js";
import type { OcrProvider, OcrResult, PdfOptions } from "../providers/types.js";

interface ExtractFixture {
  pages: Array<{ page: number; ocr_used: boolean; text: string }>;
}

function repoRoot(): string {
  // src/media/pdf/ocr/synthetic-fixture.ts → repo root is ../../../../
  return fileURLToPath(new URL("../../../..", import.meta.url));
}

const EXTRACT_PATH = () =>
  `${repoRoot()}examples/dummy-fixtures/media/pdf/extract.json`;

let cache: ExtractFixture | null = null;

function loadExtract(): ExtractFixture {
  return (cache ??= JSON.parse(readFileSync(EXTRACT_PATH(), "utf8")) as ExtractFixture);
}

class SyntheticFixtureOcrProvider implements OcrProvider {
  readonly id = "synthetic-fixture";

  /** Always available — pure offline fixture read, no binary required. */
  available(): boolean {
    return true;
  }

  async ocr(_pageImage: Uint8Array, _opts?: PdfOptions): Promise<OcrResult> {
    // Touch the fixture so a missing checked-in extract.json surfaces as a
    // provider error instead of silent canned output.
    loadExtract();
    // The scanned page in the fixture set is page 2; serve its expected OCR
    // text. Confidence is deliberately LOWER than the text layer's — OCR
    // pages reduce the weighted-mean confidence (§4.3 algorithm step 4).
    const scanned = loadExtract().pages.find((p) => p.ocr_used === true);
    return {
      text: scanned ? scanned.text : "",
      confidence: 0.8,
    };
  }
}

const INSTANCE = new SyntheticFixtureOcrProvider();

/** Self-register so getOcrProvider("synthetic-fixture") works after import. */
export function register(): void {
  registerOcrProvider(INSTANCE);
}
export { INSTANCE as syntheticFixtureOcrProvider };
