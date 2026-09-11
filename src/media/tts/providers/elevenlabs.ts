// Requirement IDs: MED-03, MED-TTS-01, MED-RES-01, GOV-MIN-04, GOV-RES-02,
// XCUT-08
// elevenlabs TTS provider — DP-C §4.4 built-in alternative (RES-03 secondary).
//
// Optional-dep style (GOV-MIN-04): uses global fetch against the
// stream-text-to-speech endpoint; absent SDK/credential surfaces as a THROWN
// MediaError at call time so RES-01 can retry/fallback. The credential VALUE
// is read via resolveCredential() using only the env var NAME held in
// credentials_env (GOV-RES-02 indirection). Model default: eleven_multilingual_v2.
//
// NATIVE STREAMING (DP-C §5.1): implements synthesizeStream by reading the
// endpoint's chunked MP3 body incrementally, so first audio can play before
// synthesis completes (MED-TTS-01) — no wrapper polyfill, no caller change.
// NONGOAL-04: `voice` is a plain provider voice-id passthrough.

import { MediaError, resolveCredential } from "../../config.js";
import { registerTtsProvider } from "./types.js";
import type { TtsChunk, TtsInput, TtsOptions, TtsProvider, TtsResult } from "./types.js";

const API = "https://api.elevenlabs.io/v1/text-to-speech";
const DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"; // neutral "Rachel" voice id
const DEFAULT_MODEL = "eleven_multilingual_v2";

function partsOf(input: TtsInput): { text: string; voice?: string } {
  return typeof input === "string" ? { text: input } : input;
}

class ElevenLabsTtsProvider implements TtsProvider {
  readonly id = "elevenlabs";

  async synthesize(input: TtsInput, opts: TtsOptions): Promise<TtsResult> {
    const { audio } = await this.requestAudio(input, opts);
    return {
      audio,
      format: opts.format ?? "mp3",
      sampleRate: opts.sampleRate ?? 44100,
      audio_ref: null,
    };
  }

  /** Native incremental delivery (§5.1): yields raw body chunks as they land. */
  async *synthesizeStream(input: TtsInput, opts: TtsOptions): AsyncIterable<TtsChunk> {
    const t0 = Date.now();
    const res = await this.open(input, opts);
    // open() guarantees a non-null body (checked below before returning).
    const reader = res.body!.getReader();
    let index = 0;
    for (;;) {
      const { done, value } = await reader.read();
      if (opts.signal?.aborted) {
        void reader.cancel().catch(() => {});
        throw new DOMException("Aborted", "AbortError");
      }
      if (done) break;
      yield {
        audio_chunk: Buffer.from(value).toString("base64"),
        delta_text: "", // byte-level stream; text alignment not provided
        index,
        is_final: false,
      };
      index += 1;
    }
    yield {
      audio_chunk: "",
      delta_text: "",
      index,
      is_final: true,
      latency_ms: Date.now() - t0,
    };
  }

  //#region internals

  private async open(input: TtsInput, opts: TtsOptions): Promise<Response> {
    const apiKey = resolveCredential({
      provider: this.id,
      credentials_env: opts.credentials_env || "ELEVENLABS_API_KEY",
    });
    const { text, voice } = partsOf(input);
    try {
      const res = await fetch(`${API}/${encodeURIComponent(voice ?? DEFAULT_VOICE_ID)}?output_format=mp3_44100_128`, {
        method: "POST",
        headers: { "xi-api-key": apiKey, "Content-Type": "application/json" },
        body: JSON.stringify({
          text,
          model_id: opts.model ?? DEFAULT_MODEL,
        }),
      });
      if (!res.ok || !res.body) {
        throw new Error(`text-to-speech HTTP ${res.status}: ${(await res.text()).slice(0, 200)}`);
      }
      return res;
    } catch (err) {
      if (err instanceof MediaError) throw err;
      throw new MediaError(
        "provider_error",
        `elevenlabs synthesis failed: ${err instanceof Error ? err.message : String(err)}`,
      );
    }
  }

  private async requestAudio(input: TtsInput, opts: TtsOptions): Promise<{ audio: Uint8Array }> {
    const res = await this.open(input, opts);
    return { audio: new Uint8Array(await res.arrayBuffer()) };
  }

  //#endregion
}

const INSTANCE = new ElevenLabsTtsProvider();

/** Self-register so getTtsProvider("elevenlabs") works after import. */
export function register(): void {
  registerTtsProvider(INSTANCE);
}
export { INSTANCE as elevenlabsTtsProvider };
