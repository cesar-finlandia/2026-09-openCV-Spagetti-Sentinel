// AUTO-GENERATED — do not edit; source: contracts/media-message.schema.json
// Requirement IDs: MED-01, MED-02
// Generated from DP-C §3.2 (json-schema-to-typescript target shape). Consumers import this
// type; never inline a UnifiedMediaMessage literal elsewhere (CI grep guard, DP-C §8.3).

export type MediaType = "stt" | "vision" | "pdf" | "tts";

export type UnifiedMediaMessage = {
  /** Modality tag. Literal per wrapper invocation; downstream switches only on this tag. */
  type: MediaType;
  /** Reference to raw input — checked-in path, stream id/handle, or text hash. Never raw bytes. */
  raw_ref: string;
  /** Extracted text: stt transcript / vision caption / pdf extracted-or-OCR text / tts echoed input. */
  text: string;
  /** Free-form structured payload where applicable; null when not applicable. */
  structured_fields: Record<string, unknown> | null;
  /** Provider-reported confidence normalized to 0..1; 0 when error != null. */
  confidence: number;
  /** True iff produced from a checked-in synthetic fixture (MED-04) or generated test data. */
  synthetic: boolean;
  /** Producer ISO-8601 UTC when normalization completed. */
  timestamp: string; // ISO-8601
  /** Effective provider id, e.g. openai-whisper, synthetic-fixture. Lowercased kebab-case. */
  provider: string;
  /** Null on success; MED-RES-02 typed code on bad input (empty_input, corrupt_file, ...). */
  error: string | null;
  /** Schema version. Additive optional field = MINOR; breaking = MAJOR + MIGRATION.md. */
  version: "1.0.0";
};
