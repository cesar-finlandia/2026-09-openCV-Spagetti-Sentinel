// Requirement IDs: MED-03, MED-RES-01, GOV-MIN-04, GOV-RES-02, XCUT-08
// deepgram STT provider — DP-C §4.1 built-in (optional, RES-03 secondary).
//
// Optional-dep style (GOV-MIN-04): no SDK is imported; transcription goes over
// HTTPS via fetch when selected. A missing DEEPGRAM_API_KEY (via
// credentials_env NAME indirection) throws MediaError("missing_credentials")
// at CALL time — never at startup — so RES-01 can fall back to the secondary
// provider. Provider/network failures throw MediaError("provider_error");
// they are never swallowed into UnifiedMediaMessage.error (DP-C §7.1/§7.2).

import { MediaError, resolveCredential } from "../../config.js";
import { registerSttProvider } from "./types.js";
import type { AudioInput, SttOptions, SttProvider, SttResult } from "./types.js";

const DEFAULT_URL = "https://api.deepgram.com/v1/listen";

function inputBytes(input: AudioInput): Uint8Array {
  if ("path" in input) {
    // Lazy import keeps this provider importable in non-Node runtimes.
    return requireFs().readFileSync(input.path);
  }
  if ("buffer" in input) return Buffer.from(input.buffer);
  if ("base64" in input) return Buffer.from(input.base64, "base64");
  throw new MediaError("provider_error", "stream input unsupported by deepgram; buffer the stream first");
}

function requireFs(): { readFileSync(p: string): Buffer } {
  // eslint-disable-next-line @typescript-eslint/no-require-imports -- lazy CJS interop for optional runtime
  const { createRequire } = require("node:module");
  return createRequire(import.meta.url)("node:fs") as { readFileSync(p: string): Buffer };
}

interface DeepgramWord {
  word?: string;
  punctuated_word?: string;
  start?: number;
  end?: number;
  confidence?: number;
}

class DeepgramSttProvider implements SttProvider {
  readonly id = "deepgram";

  async transcribe(input: AudioInput, opts: SttOptions): Promise<SttResult> {
    // Credential first — throws MediaError("missing_credentials") when unset.
    const apiKey = resolveCredential({
      provider: "deepgram",
      credentials_env: opts.credentials_env || "DEEPGRAM_API_KEY",
    });

    const bytes = inputBytes(input);
    const params = new URLSearchParams({
      model: opts.model ?? "nova-2",
      smart_format: "false",
      ...(opts.language ? { language: opts.language } : {}),
    });

    try {
      const res = await fetch(`${DEFAULT_URL}?${params.toString()}`, {
        method: "POST",
        headers: {
          Authorization: `Token ${apiKey}`,
          "Content-Type": mimeFor(input),
        },
        body: new Uint8Array(bytes),
        signal: opts.timeout_ms ? AbortSignal.timeout(opts.timeout_ms) : undefined,
      });
      if (!res.ok) {
        throw new MediaError(
          "provider_error",
          `deepgram listen failed with HTTP ${res.status}`,
        );
      }
      const json = (await res.json()) as {
        results?: {
          channels?: Array<{
            alternatives?: Array<{
              transcript?: string;
              confidence?: number;
              words?: DeepgramWord[];
            }>;
          }>;
          metadata?: { duration?: number };
        };
      };
      const alt = json.results?.channels?.[0]?.alternatives?.[0];
      const text = typeof alt?.transcript === "string" ? alt.transcript : "";
      const confidence = clampConfidence(alt?.confidence);
      const words = (alt?.words ?? []).map((w) => ({
        text: w.punctuated_word ?? w.word ?? "",
        start_ms: Math.round((w.start ?? 0) * 1000),
        end_ms: Math.round((w.end ?? 0) * 1000),
      }));
      return {
        text,
        confidence,
        structured: {
          language: opts.language ?? null,
          duration_ms:
            json.results?.metadata?.duration != null
              ? Math.round(json.results.metadata.duration * 1000)
              : null,
          words,
          model: opts.model ?? "nova-2",
        },
      };
    } catch (err) {
      if (err instanceof MediaError) throw err;
      throw new MediaError(
        "provider_error",
        `deepgram transcription failed: ${err instanceof Error ? err.message : String(err)}`,
      );
    }
  }
}

function mimeFor(input: AudioInput): string {
  const encoding =
    ("encoding" in input && input.encoding) ||
    ("path" in input ? input.path.split(".").pop() ?? "" : "");
  switch (encoding.toLowerCase()) {
    case "wav":
    case "wave":
      return "audio/wav";
    case "mp3":
      return "audio/mp3";
    case "webm":
      return "audio/webm";
    case "ogg":
      return "audio/ogg";
    default:
      return "audio/wav";
  }
}

function clampConfidence(c: unknown): number {
  return typeof c === "number" && Number.isFinite(c) ? Math.min(1, Math.max(0, c)) : 0.9;
}

const INSTANCE = new DeepgramSttProvider();

/** Self-register so getSttProvider("deepgram") works after import. */
export function register(): void {
  registerSttProvider(INSTANCE);
}
export { INSTANCE as deepgramProvider };
