// Requirement IDs: GOV-RES-04, MED-RES-02, XCUT-08
// "none" OCR provider — DP-C §4.3 built-in.
//
// Explicit disabled marker: the wrapper checks id==="none" BEFORE invoking
// ocr(), so ocr() here is a hard guard only. Selecting "none" (or leaving
// MED_OCR_PROVIDER unset to the safe default) means scanned pages keep their
// short text-layer content with ocr_used:false and lowered confidence —
// graceful degrade, never a crash (GOV-RES-04).

import { MediaError } from "../../config.js";
import { registerOcrProvider } from "../providers/types.js";
import type { OcrProvider, OcrResult, PdfOptions } from "../providers/types.js";

class NoneOcrProvider implements OcrProvider {
  readonly id = "none";

  /** "Available" as a registry citizen; the wrapper still treats id "none"
   * as OCR-disabled before ever calling ocr(). */
  available(): boolean {
    return true;
  }

  async ocr(_pageImage: Uint8Array, _opts?: PdfOptions): Promise<OcrResult> {
    throw new MediaError("provider_error", 'OCR is disabled (ocr_provider "none")');
  }
}

const INSTANCE = new NoneOcrProvider();

/** Self-register so getOcrProvider("none") works after import. */
export function register(): void {
  registerOcrProvider(INSTANCE);
}
export { INSTANCE as noneOcrProvider };
