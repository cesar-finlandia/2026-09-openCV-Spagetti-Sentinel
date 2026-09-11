// Requirement IDs: MED-03, GOV-RES-04, GOV-MIN-04, MED-RES-02 | DP-C §4.3/§7.2/§10.1
// tesseract OCR provider — DP-C §4.3 optional built-in (§10.1 OPTIONAL extra).
//
// Shells out to the system `tesseract` binary (no npm/pip OCR dependency).
// Binary availability is detected ONCE via a bounded `tesseract --version`
// probe and cached; when absent the wrapper degrades gracefully per §7.2 row
// "OCR unavailable": text-layer-only result, ocr_provider:"none", lowered
// confidence, NO throw (GOV-RES-04). Hard runtime failures throw MediaError
// so RES-01 can act.

import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";
import { MediaError } from "../../config.js";
import { registerOcrProvider } from "../providers/types.js";
import type { OcrProvider, OcrResult, PdfOptions } from "../providers/types.js";

/** Bounded probe/run time — the wrapper additionally enforces timeout_ms. */
const TESSERACT_TIMEOUT_MS = 10_000;

let availabilityCache: boolean | null = null;

function detectBinary(): boolean {
  if (availabilityCache !== null) return availabilityCache;
  try {
    const probe = spawnSync("tesseract", ["--version"], {
      timeout: 5_000,
      encoding: "utf8",
      windowsHide: true,
    });
    availabilityCache = !probe.error && probe.status === 0;
  } catch {
    availabilityCache = false;
  }
  return availabilityCache;
}

class TesseractOcrProvider implements OcrProvider {
  readonly id = "tesseract";

  /** False when the system binary is missing → wrapper degrades to
   * text-layer-only with ocr_provider:"none" (never throws). */
  available(): boolean {
    return detectBinary();
  }

  async ocr(pageImage: Uint8Array, opts?: PdfOptions): Promise<OcrResult> {
    if (!detectBinary()) {
      // Wrapper normally guards this; kept as a hard guard for direct use.
      throw new MediaError(
        "provider_error",
        'tesseract binary not available (ocr_provider should degrade to "none")',
      );
    }
    const dir = mkdtempSync(join(tmpdir(), "media-pdf-ocr-"));
    const imgPath = join(dir, "page.png");
    try {
      writeFileSync(imgPath, pageImage);
      const args = [imgPath, "stdout"];
      if (opts?.ocrLanguages) args.push("-l", opts.ocrLanguages);
      const run = spawnSync("tesseract", args, {
        timeout: TESSERACT_TIMEOUT_MS,
        encoding: "utf8",
        windowsHide: true,
      });
      if (run.error || run.status !== 0) {
        const detail = run.error?.message ?? run.stderr ?? `exit ${run.status}`;
        throw new MediaError("provider_error", `tesseract failed: ${detail.trim()}`);
      }
      return { text: (run.stdout ?? "").trim(), confidence: 0.75 };
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  }
}

const INSTANCE = new TesseractOcrProvider();

/** Self-register so getOcrProvider("tesseract") works after import. */
export function register(): void {
  registerOcrProvider(INSTANCE);
}
export { INSTANCE as tesseractOcrProvider };

/** Test/diagnostic hook: reset the cached binary probe result. */
export function resetAvailabilityCache(): void {
  availabilityCache = null;
}

/** Exposed for wrapper-level rendering fallbacks that need fixture bytes. */
export function readFixtureBytes(path: string): Uint8Array {
  return new Uint8Array(readFileSync(path));
}
