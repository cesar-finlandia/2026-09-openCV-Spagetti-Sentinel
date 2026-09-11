// Requirement IDs: MED-03, MED-TTS-01, MED-RES-01, GOV-MIN-04, GOV-RES-02,
// XCUT-08
// openai-tts provider — DP-C §4.4 built-in default (audio/speech API).
//
// Request/RESPONSE only today: no native synthesizeStream is exposed, so the
// wrapper polyfills streaming by slicing the synthesized bytes (DP-C §5.1) and
// the MED-TTS-01 incremental contract holds without caller changes.
//
// Optional-dep style (GOV-MIN-04): uses global fetch; an absent credential
// surfaces as a THROWN MediaError at call time so RES-01 can retry/fallback.
// The credential VALUE is read via resolveCredential() using only the env var
// NAME held in credentials_env (GOV-RES-02 indirection). Model default tts-1.
// NONGOAL-04: `voice` is a plain provider voice id passthrough ("alloy"…).

import { MediaError, resolveCredential } from "../../config.js";
import { registerTtsProvider } from "./types.js";
import type { TtsInput, TtsOptions, TtsProvider, TtsResult } from "./types.js";

const DEFAULT_SAMPLE_RATES: Record<string, number> = { mp3: 44100, wav: 44100, pcm: 24000 };

function textOf(input: TtsInput): string {
  return typeof input === "string" ? input : input.text;
}

class OpenaiTtsProvider implements TtsProvider {
  readonly id = "openai-tts";

  async synthesize(input: TtsInput, opts: TtsOptions): Promise<TtsResult> {
    // Credential first (call-time check, GOV-RES-02) — throws MediaError(
    // "missing_credentials") when the named env var is unset.
    const apiKey = resolveCredential({
      provider: this.id,
      credentials_env: opts.credentials_env || "OPENAI_API_KEY",
    });
    const format = opts.format ?? "mp3";
    const model = opts.model ?? "tts-1";
    try {
      const res = await fetch("https://api.openai.com/v1/audio/speech", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${apiKey}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          model,
          input: textOf(input),
          voice: opts.voice ?? "alloy",
          response_format: format,
        }),
      });
      if (!res.ok) {
        throw new Error(`audio/speech HTTP ${res.status}: ${(await res.text()).slice(0, 200)}`);
      }
      const audio = new Uint8Array(await res.arrayBuffer());
      return {
        audio,
        format,
        sampleRate: opts.sampleRate ?? DEFAULT_SAMPLE_RATES[format] ?? 24000,
        audio_ref: null, // inline base64 in structured_fields (§4.4 output note)
      };
    } catch (err) {
      if (err instanceof MediaError) throw err;
      throw new MediaError(
        "provider_error",
        `openai-tts synthesis failed: ${err instanceof Error ? err.message : String(err)}`,
      );
    }
  }
}

const INSTANCE = new OpenaiTtsProvider();

/** Self-register so getTtsProvider("openai-tts") works after import. */
export function register(): void {
  registerTtsProvider(INSTANCE);
}
export { INSTANCE as openaiTtsProvider };
