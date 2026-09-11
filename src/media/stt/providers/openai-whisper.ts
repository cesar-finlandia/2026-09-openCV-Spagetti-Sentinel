// Requirement IDs: MED-03, MED-RES-01, GOV-MIN-04, GOV-RES-02, XCUT-08
// openai-whisper STT provider — DP-C §4.1 built-in (default per config/media.json).
//
// Optional-dep style (GOV-MIN-04): the `openai` SDK is required lazily on first
// call; absent SDK or credential surfaces as a THROWN MediaError at call time
// so RES-01 can retry/fallback — never a startup crash, never a swallowed
// error. The credential VALUE is read via resolveCredential() using only the
// env var NAME held in credentials_env (GOV-RES-02 indirection).
//
// Model default: whisper-1 (config slice `model`). No persona prompt; the
// optional promptHint is a generic verbatim hint passed through as the API
// `prompt` field when set (MED-REU-01).

import { readFileSync } from "node:fs";
import { MediaError, resolveCredential } from "../../config.js";
import { registerSttProvider } from "./types.js";
import type { AudioInput, SttOptions, SttProvider, SttResult } from "./types.js";

/** Minimal structural surface of the lazily-required OpenAI client we use. */
interface WhisperClientLike {
  audio: {
    transcriptions: {
      create(args: Record<string, unknown>): Promise<unknown>;
    };
  };
}

function requireOpenAi(apiKey: string): WhisperClientLike {
  try {
    // Optional peer dependency — loaded only when this provider is selected.
    const Ctor = requireOpenAiModule();
    return new Ctor({ apiKey }) as WhisperClientLike;
  } catch (err) {
    throw new MediaError(
      "provider_error",
      `openai SDK unavailable for provider openai-whisper (${err instanceof Error ? err.message : String(err)})`,
    );
  }
}

let openAiCtorCache: (new (opts: { apiKey: string }) => unknown) | null = null;
function requireOpenAiModule(): new (opts: { apiKey: string }) => unknown {
  const cached = openAiCtorCache;
  if (cached !== null) return cached;
  // eslint-disable-next-line @typescript-eslint/no-require-imports -- optional dep, lazy CJS interop
  const { createRequire } = require("node:module");
  const req = createRequire(import.meta.url);
  const Ctor = (req("openai").default ?? req("openai")) as new (opts: {
    apiKey: string;
  }) => unknown;
  openAiCtorCache = Ctor;
  return Ctor;
}

function toBlobOrFile(input: AudioInput): File {
  if ("path" in input) {
    const data = readFileSync(input.path);
    return new File([data], input.path.split(/[\\/]/).pop() ?? "audio.wav");
  }
  if ("buffer" in input) {
    return new File([Buffer.from(input.buffer)], `audio.${input.encoding ?? "wav"}`);
  }
  if ("base64" in input) {
    return new File([Buffer.from(input.base64, "base64")], `audio.${input.encoding ?? "wav"}`);
  }
  throw new MediaError("provider_error", "stream input unsupported by openai-whisper; buffer the stream first");
}

class OpenaiWhisperSttProvider implements SttProvider {
  readonly id = "openai-whisper";

  async transcribe(input: AudioInput, opts: SttOptions): Promise<SttResult> {
    // Credential first (call-time check, GOV-RES-02) — throws MediaError(
    // "missing_credentials") when the named env var is unset.
    const apiKey = resolveCredential({
      provider: "openai-whisper",
      credentials_env: opts.credentials_env || "OPENAI_API_KEY",
    });
    const client = requireOpenAi(apiKey);
    try {
      const file = toBlobOrFile(input);
      const result = (await client.audio.transcriptions.create({
        file,
        model: opts.model ?? "whisper-1",
        ...(opts.language ? { language: opts.language } : {}),
        ...(opts.promptHint ? { prompt: opts.promptHint } : {}),
      })) as { text?: string };

      const text = typeof result?.text === "string" ? result.text : "";
      return {
        text,
        confidence: 0.9, // whisper does not report confidence; neutral default
        structured: {
          language: opts.language ?? null,
          duration_ms: null,
          words: [],
          model: opts.model ?? "whisper-1",
        },
      };
    } catch (err) {
      if (err instanceof MediaError) throw err;
      throw new MediaError(
        "provider_error",
        `openai-whisper transcription failed: ${err instanceof Error ? err.message : String(err)}`,
      );
    }
  }
}

const INSTANCE = new OpenaiWhisperSttProvider();

/** Self-register so getSttProvider("openai-whisper") works after import. */
export function register(): void {
  registerSttProvider(INSTANCE);
}
export { INSTANCE as openaiWhisperProvider };
