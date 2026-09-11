// Requirement IDs: MED-RES-01, MED-03, RES-01, RES-03, RES-REU-02, GOV-RES-01, XCUT-08
// Optional ergonomic sugar for wiring media wrappers into RES-01 — DP-C §7.1.
// withMediaResilience(fn, secondaryFn?, resilienceConfig?) delegates to
// withResilience from src/resilience; the secondary provider callable is passed
// out-of-band via deps.secondaryProvider (DP-A §4.2, never serialized).
//
// Default resilience config per DP-C §7.1: { timeout_ms:15000, retries:1,
// fallback_chain:{ order:["secondary_provider","cache","replay","none"] } }.
// The secondary_provider STEP is explicitly enabled because DP-A defaults it to
// disabled — without {enabled:true} the chain would skip straight to cache.
//
// Consumers may use withResilience directly — this helper is sugar only.
// Domain-free (GOV-REU-02); no modality-specific imports (MED-REU-02).

import type { ResilienceConfig, DegradedResult } from "../resilience/index.js";
import type { UnifiedMediaMessage } from "./media-message.js";
import { withResilience } from "../resilience/index.js";

//#region Default config (DP-C §7.1)

/**
 * Frozen default ResilienceConfig: 15 s timeout, 1 retry, full fallback chain
 * starting at the secondary provider (RES-03), then cache, replay, degrade.
 */
export const DEFAULT_MEDIA_RESILIENCE_CONFIG: ResilienceConfig = {
  timeout_ms: 15000,
  retries: 1,
  fallback_chain: {
    order: ["secondary_provider", "cache", "replay", "none"],
    // DP-A defaults this step to enabled:false; media wants it ON when a
    // secondaryFn is supplied.
    secondary_provider: { enabled: true },
  },
};

//#endregion

//#region withMediaResilience (DP-C §7.1)

/**
 * Wrap a media wrapper closure (`() => Promise<UnifiedMediaMessage>`, zero
 * required args — RES-REU-02 closure-friendly) with timeout+retry+fallback.
 *
 * - `fn`          primary call, e.g. `() => transcribe(input, primaryOpts)`
 * - `secondaryFn` optional RES-03 secondary-provider call with identical I/O
 *                 shape, e.g. `() => transcribe(input, {...opts, provider:
 *                 secondaryId})`; passed out-of-band via deps.secondaryProvider
 * - `resilienceConfig` optional override; defaults to DEFAULT_MEDIA_RESILIENCE_CONFIG
 *
 * Returns an async callable resolving to `T` on success or a DegradedResult
 * when every fallback step is exhausted — never throws unhandled (RES-RES-03).
 */
export function withMediaResilience<T extends UnifiedMediaMessage>(
  fn: () => Promise<T>,
  secondaryFn?: () => Promise<T>,
  resilienceConfig?: ResilienceConfig,
): () => Promise<T | DegradedResult> {
  return withResilience(fn, resilienceConfig ?? DEFAULT_MEDIA_RESILIENCE_CONFIG, {
    ...(secondaryFn !== undefined ? { secondaryProvider: secondaryFn } : {}),
  });
}

//#endregion
