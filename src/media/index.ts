// Requirement IDs: MED-01, MED-02, MED-03, MED-REU-02, XCUT-07
// Barrel re-exports ONLY — DP-C §8.1/§8.2.
//
// NOTE: direct entrypoint imports remain the PREFERRED surface
// (`import { transcribe } from "src/media/stt"` etc.). Importing from this
// barrel transitively evaluates all four modality providers, which violates
// MED-REU-02 independent importability — use it only when you genuinely want
// the whole media package.

export * from "./media-message.js";
export {
  MEDIA_SAFE_DEFAULTS,
  MediaError,
  isModalityKey,
  loadMediaConfig,
  resolveCredential,
  warn,
} from "./config.js";
export type { MediaConfig, ModalityKey, ResolvedMediaConfig } from "./config.js";
export { DEFAULT_MEDIA_RESILIENCE_CONFIG, withMediaResilience } from "./resilient.js";

export {
  addSttProvider,
  transcribe,
} from "./stt.js";
export type { AudioInput as SttAudioInput, SttOptions } from "./stt.js";

export {
  addVisionProvider,
  caption,
  defaultPrompt,
  resolvePrompt,
  validateImageBuffer,
} from "./vision.js";
export type { ImageInput as VisionImageInput, VisionOptions } from "./vision.js";

export {
  addOcrProvider,
  addPdfTextProvider,
  extract,
  validatePdfBuffer,
} from "./pdf.js";
export type { PdfInput as PdfDocumentInput, PdfOptions } from "./pdf.js";

export {
  BargeInController,
  TtsInputError,
  addTtsProvider,
  synthesize,
  synthesizeStream,
  validateTtsInput,
} from "./tts.js";
export type { TtsChunk, TtsFormat, TtsInput, TtsOptions } from "./tts.js";
