// Requirement IDs: MED-03, MED-REU-01, RES-03, RES-04, GOV-RES-02, XCUT-08
// MediaConfig load/merge/validate — DP-C §6.1 (schema + resolution precedence),
// §7.2 (error contract), §7.3 (safe defaults on missing/malformed config).
//
// Resolution precedence (lowest → highest, DP-C §6.1):
//   1. config/media.json checked-in defaults (per-modality slice)
//   2. per-call MediaConfig overrides passed to the loader/wrapper
//   3. MED_* env overrides (operator swap mid-event, zero code change)
//
// credentials_env holds ONLY the env var NAME; the value is read at call time
// via resolveCredential(). A missing credential throws MediaError(
// "missing_credentials") at CALL time — never at startup (GOV-RES-02).
//
// Malformed/missing media config never crashes startup: invalid merges are
// warned about and replaced by safe defaults { provider:"synthetic-fixture",
// timeout_ms:15000, ocr_provider:"none" } (DP-C §7.3).
//
// Domain-free (GOV-REU-02); imports only node stdlib + src/resilience (RES-REU-01).

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { validate } from "../resilience/index.js";

//#region Types (mirror of contracts/media-config.schema.json — single source §8.3)

/** Modality slice keys in config/media.json and the four wrapper entrypoints. */
export type ModalityKey = "stt" | "vision" | "pdf" | "tts";

/**
 * Per-wrapper provider config (DP-C §6.1). Partial form: any field except
 * `provider` may be omitted and is filled from lower-precedence sources.
 */
export interface MediaConfig {
  /** Primary provider id for this modality (e.g. openai-whisper, synthetic-fixture). */
  provider: string;
  /** Optional RES-03 secondary provider id; null = no secondary. */
  secondary_provider?: string | null;
  /** Per-call timeout forwarded to RES-01 (default 15000). */
  timeout_ms?: number;
  /** RES-02 retry count hint (default 1). */
  retries?: number;
  /** Provider model override; null means provider default. */
  model?: string | null;
  /** Generic prompt override (MED-REU-01); null means wrapper default. */
  prompt?: string | null;
  /** PDF-only OCR engine id ("tesseract") or null/"none" to disable. */
  ocr_provider?: string | null;
  /** Env var NAME holding the credential — never the value itself. */
  credentials_env?: string;
  /** Provider-specific passthrough (voice, sampleRate, language). */
  options?: Record<string, unknown>;
}

/** Fully-resolved config returned by loadMediaConfig (all optional fields filled). */
export interface ResolvedMediaConfig extends Required<Omit<MediaConfig, "options">> {
  options?: Record<string, unknown>;
}

//#endregion

//#region Errors (DP-C §7.2 error contract)

/** Codes used across the media wrappers. Provider-side failures THROW so
 * RES-01 can retry/fallback; bad-input errors are NOT thrown (they are
 * returned as UnifiedMediaMessage.error per DP-C §7.2). */
export type MediaErrorCode = "provider_error" | "unknown_provider" | "missing_credentials";

export class MediaError extends Error {
  readonly code: MediaErrorCode;

  constructor(code: MediaErrorCode, message?: string) {
    super(message ?? code);
    this.name = "MediaError";
    this.code = code;
  }
}

//#endregion

//#region Safe defaults + schema access (DP-C §7.3, GOV-RES-02)

export function warn(message: string): void {
  console.warn(`[media] warn: ${message}`);
}

/** Hardcoded safe defaults used when a merged config fails validation or no
 * usable source exists. Always works offline (synthetic-fixture), never hangs. */
export const MEDIA_SAFE_DEFAULTS: ResolvedMediaConfig = Object.freeze({
  provider: "synthetic-fixture",
  secondary_provider: null,
  timeout_ms: 15000,
  retries: 1,
  model: null,
  prompt: null,
  ocr_provider: "none", // conservative: disable OCR fallback when config is untrusted
  credentials_env: "",
});

function repoRoot(): string {
  // src/media/config.ts → repo root is ../../
  return fileURLToPath(new URL("../..", import.meta.url));
}

const SCHEMA_PATH = () => `${repoRoot()}contracts/media-config.schema.json`;
const DEFAULTS_PATH = () => `${repoRoot()}config/media.json`;

let schemaCache: object | null = null;
function mediaConfigSchema(): object {
  return (schemaCache ??= JSON.parse(readFileSync(SCHEMA_PATH(), "utf8")) as object);
}

//#endregion

//#region Checked-in defaults file (config/media.json)

type DefaultsFile = Partial<Record<ModalityKey, MediaConfig>>;

let defaultsCache: DefaultsFile | null = null;

/** Read + cache config/media.json. Missing/corrupt file → {} with a warn
 * (GOV-RES-02): never crashes startup; callers fall through to safe defaults. */
function loadDefaultsFile(): DefaultsFile {
  if (defaultsCache) return defaultsCache;
  try {
    const raw = JSON.parse(readFileSync(DEFAULTS_PATH(), "utf8")) as unknown;
    if (raw === null || typeof raw !== "object" || Array.isArray(raw)) {
      throw new Error("config/media.json root is not an object");
    }
    // $comment and any non-slice keys are ignored by the per-modality lookup.
    defaultsCache = raw as DefaultsFile;
  } catch (err) {
    warn(`config/media.json unreadable (${err instanceof Error ? err.message : String(err)}); using safe defaults`);
    defaultsCache = {};
  }
  return defaultsCache;
}

//#endregion

//#region MED_* env overrides (DP-C §6.1 precedence tier 3)

type EnvSource = Record<string, string | undefined>;

/** Operator overrides for one modality slice, from MED_* env vars. Empty/absent
 * values are skipped so a partially-set env cannot blank a field. */
function envOverrides(modality: ModalityKey, env: EnvSource): Partial<MediaConfig> {
  const m = modality.toUpperCase();
  const out: Partial<MediaConfig> = {};
  const provider = env[`MED_${m}_PROVIDER`];
  const secondary = env[`MED_${m}_SECONDARY_PROVIDER`];
  const prompt = env[`MED_${m}_PROMPT`];
  const ocr = modality === "pdf" ? env.MED_OCR_PROVIDER : undefined;
  if (provider) out.provider = provider;
  if (secondary) out.secondary_provider = secondary;
  if (prompt) out.prompt = prompt;
  if (ocr) out.ocr_provider = ocr;
  return out;
}

//#endregion

//#region Merge + validate + resolve (DP-C §6.1, §7.3)

const MODALITIES: readonly ModalityKey[] = ["stt", "vision", "pdf", "tts"];

export function isModalityKey(value: string): value is ModalityKey {
  return (MODALITIES as readonly string[]).includes(value);
}

/** Schema-declared defaults (DP-C §6.1): filled after merging, before validation.
 * ocr_provider is PDF-only per the schema description — left unset elsewhere. */
function withSchemaDefaults(merged: Partial<MediaConfig>, modality: ModalityKey): ResolvedMediaConfig {
  return {
    provider: merged.provider!,
    secondary_provider: merged.secondary_provider ?? null,
    timeout_ms: merged.timeout_ms ?? 15000,
    retries: merged.retries ?? 1,
    model: merged.model ?? null,
    prompt: merged.prompt ?? null,
    ...(modality === "pdf" ? { ocr_provider: merged.ocr_provider ?? "tesseract" } : { ocr_provider: null }),
    credentials_env: merged.credentials_env ?? "",
    ...(merged.options !== undefined ? { options: merged.options } : {}),
  } as ResolvedMediaConfig;
}

/**
 * Resolve one modality's MediaConfig: config/media.json slice < per-call
 * `overrides` < MED_* env vars (lowest → highest, DP-C §6.1). The merged result
 * is validated via RES-04 validate(media-config.schema); on failure a warn is
 * logged and MEDIA_SAFE_DEFAULTS returned (GOV-RES-02, DP-C §7.3). Never throws.
 */
export function loadMediaConfig(
  modality: ModalityKey,
  overrides?: Partial<MediaConfig> | null,
  env: EnvSource = process.env as EnvSource,
): ResolvedMediaConfig {
  try {
    const base = loadDefaultsFile()[modality] ?? {};
    const merged: Partial<MediaConfig> = { ...base, ...compact(overrides), ...envOverrides(modality, env) };
    if (merged.provider === undefined || merged.provider === null || merged.provider === "") {
      // Schema requires provider; missing entirely means no usable source at all.
      warn(`media config missing provider for ${modality}; using safe defaults`);
      return { ...MEDIA_SAFE_DEFAULTS };
    }
    const resolved = withSchemaDefaults(merged, modality);
    const result = validate(mediaConfigSchema(), resolved);
    if (!result.valid) {
      const first = result.errors[0];
      warn(
        `media config field ${first?.path ?? "/"} invalid (${first?.message ?? "validation failed"}); using safe defaults`,
      );
      return { ...MEDIA_SAFE_DEFAULTS };
    }
    return resolved;
  } catch (err) {
    // GOV-RES-04 containment: loader must never crash startup or a wrapper call.
    warn(`media config resolution failed (${err instanceof Error ? err.message : String(err)}); using safe defaults`);
    return { ...MEDIA_SAFE_DEFAULTS };
  }
}

/** Drop undefined values so per-call overrides cannot shadow lower tiers with holes. */
function compact(cfg?: Partial<MediaConfig> | null): Partial<MediaConfig> {
  if (!cfg) return {};
  const out: Partial<MediaConfig> = {};
  for (const [k, v] of Object.entries(cfg)) {
    if (v !== undefined) (out as Record<string, unknown>)[k] = v;
  }
  return out;
}

//#endregion

//#region Credential indirection (DP-C §6.1/§7.3 — NAME only, read at call time)

/**
 * Read the credential VALUE at call time via the env var NAME held in
 * credentials_env. Missing/unset value throws MediaError("missing_credentials")
 * here — at call time — so RES-01 can retry/fallback (never at startup).
 * An empty credentials_env means the provider needs no credential.
 */
export function resolveCredential(config: MediaConfig, env: EnvSource = process.env as EnvSource): string {
  const name = config.credentials_env;
  if (!name) return "";
  const value = env[name];
  if (value === undefined || value === "") {
    throw new MediaError("missing_credentials", `credential env var ${name} is not set`);
  }
  return value;
}

//#endregion
