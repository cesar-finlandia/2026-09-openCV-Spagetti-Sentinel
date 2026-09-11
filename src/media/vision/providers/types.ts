// Requirement IDs: MED-01, MED-03, MED-REU-01, MED-REU-02, RES-03, GOV-MIN-04, XCUT-08
// Vision provider abstraction + runtime registry — DP-C §4.2.
//
// Providers implement VisionProvider and register themselves via
// registerVisionProvider(); the wrapper resolves getVisionProvider(
// config.provider) AT CALL TIME so MED_VISION_PROVIDER env swaps need zero
// code change (MED-03). A missing id returns null → wrapper throws
// MediaError("unknown_provider") per DP-C §7.2 (never silently falls back).
//
// Isolation (MED-REU-02): this file imports nothing outside src/media shared
// surfaces (media-message/config types) — never stt/pdf/tts (CI grep guard,
// DP-C §8.1).

import { readFileSync } from "node:fs";
import type { MediaConfig } from "../../config.js";

/** Raw image input variants accepted by caption() — DP-C §4.2 ImageInput.
 * Exactly one variant key must be present; url fetch is optional and disabled
 * in offline mode (NETWORK=disabled → unsupported_format at the wrapper). */
export type ImageInput =
  | { path: string }
  | { buffer: Uint8Array; mime?: string }
  | { base64: string; mime: string }
  | { url: string };

/** Per-wrapper options: MediaConfig slice + generic prompt override only
 * (MED-REU-01 — no persona/domain vocabulary; default comes from
 * src/media/vision/default-prompt.txt). */
export type VisionOptions = Partial<MediaConfig> & {
  /** Generic instruction, e.g. "Describe the contents of this image".
   * Domain/persona prompts (second-person role assignments) are forbidden
   * by CI grep guard (GOV-REU-02). */
  prompt?: string;
  /** Cap on generated caption length (provider max_tokens). */
  maxTokens?: number;
};

/** Normalized provider result — wrapper maps it onto UnifiedMediaMessage. */
export interface VisionResult {
  text: string;
  /** Confidence normalized to 0..1. */
  confidence: number;
  /** objects[] / dimensions / model payload, or null when unavailable. */
  structured: Record<string, unknown> | null;
}

/**
 * One image-captioning backend. Implementations MUST throw on failure
 * (network, rate limit, missing credentials) so RES-01 can retry/fallback
 * (RES-REU-02); they never return error-bearing results for provider-side
 * problems.
 */
export interface VisionProvider {
  /** Lowercase kebab-case id, e.g. "openai-gpt4o-vision", "synthetic-fixture". */
  readonly id: string;
  caption(input: ImageInput, opts: VisionOptions): Promise<VisionResult>;
}

//#region Generic default prompt (MED-REU-01 / DP-C §6.2)

let defaultPromptCache: string | null = null;

/** The checked-in, domain-free default instruction from
 * src/media/vision/default-prompt.txt (single source, no persona wording).
 * Used when config.vision.prompt is null and no per-call/env override exists. */
export function defaultPrompt(): string {
  return (defaultPromptCache ??= readFileSync(
    new URL("../default-prompt.txt", import.meta.url),
    "utf8",
  ).trim());
}

//#endregion

//#region Runtime registry (DP-C §4.2 provider swap without code change)

const REGISTRY = new Map<string, VisionProvider>();

/** Register (or replace) a provider under its own id. Idempotent per id. */
export function registerVisionProvider(p: VisionProvider): void {
  REGISTRY.set(p.id, p);
}

/** Resolve by id at call time; null when unknown → caller throws
 * MediaError("unknown_provider") (DP-C §7.2 malformed-config row). */
export function getVisionProvider(id: string): VisionProvider | null {
  return REGISTRY.get(id) ?? null;
}

/** All registered ids (diagnostics/tests only — never used for resolution). */
export function listVisionProviders(): string[] {
  return [...REGISTRY.keys()].sort();
}

//#endregion
