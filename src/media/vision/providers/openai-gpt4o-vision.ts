// Requirement IDs: MED-03, MED-RES-01, MED-REU-01, GOV-MIN-04, GOV-RES-02, XCUT-08
// openai-gpt4o-vision provider — DP-C §4.2 built-in (default per §10.1).
//
// Optional-dep style (GOV-MIN-04): the `openai` SDK is required lazily on first
// call; absent SDK or credential surfaces as a THROWN MediaError at call time
// so RES-01 can retry/fallback — never a startup crash, never a swallowed
// error. The credential VALUE is read via resolveCredential() using only the
// env var NAME held in credentials_env (GOV-RES-02 indirection).
//
// Model default: gpt-4o (config slice `model`). Prompt: generic instruction
// from VisionOptions.prompt (wrapper fills it from default-prompt.txt when no
// override — MED-REU-01); url inputs are passed through as image_url.

import { readFileSync } from "node:fs";
import { MediaError, resolveCredential } from "../../config.js";
import { defaultPrompt, registerVisionProvider } from "./types.js";
import type { ImageInput, VisionOptions, VisionProvider, VisionResult } from "./types.js";

/** Minimal structural surface of the lazily-required OpenAI client we use. */
interface ChatClientLike {
  chat: {
    completions: {
      create(args: Record<string, unknown>): Promise<unknown>;
    };
  };
}

function requireOpenAi(apiKey: string): ChatClientLike {
  try {
    const Ctor = requireOpenAiModule();
    return new Ctor({ apiKey }) as ChatClientLike;
  } catch (err) {
    throw new MediaError(
      "provider_error",
      `openai SDK unavailable for provider openai-gpt4o-vision (${err instanceof Error ? err.message : String(err)})`,
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

const MIME_BY_EXT: Record<string, string> = {
  png: "image/png",
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
  webp: "image/webp",
};

/** Materialize any input variant into an OpenAI image_url payload:
 * remote urls pass through; path/buffer/base64 become data URIs. */
function toImageUrl(input: ImageInput): string {
  if ("url" in input) return input.url;
  if ("base64" in input) return `data:${input.mime};base64,${input.base64}`;
  if ("buffer" in input) {
    const mime = input.mime ?? "image/png";
    return `data:${mime};base64,${Buffer.from(input.buffer).toString("base64")}`;
  }
  const ext = (input.path.split(".").pop() ?? "png").toLowerCase();
  const mime = MIME_BY_EXT[ext] ?? "image/png";
  return `data:${mime};base64,${readFileSync(input.path).toString("base64")}`;
}

class OpenaiGpt4oVisionProvider implements VisionProvider {
  readonly id = "openai-gpt4o-vision";

  async caption(input: ImageInput, opts: VisionOptions): Promise<VisionResult> {
    // Credential first (call-time check, GOV-RES-02) — throws MediaError(
    // "missing_credentials") when the named env var is unset.
    const apiKey = resolveCredential({
      provider: this.id,
      credentials_env: opts.credentials_env || "OPENAI_API_KEY",
    });
    const client = requireOpenAi(apiKey);
    const model = opts.model ?? "gpt-4o";
    const prompt = opts.prompt ?? defaultPrompt();
    try {
      const result = (await client.chat.completions.create({
        model,
        max_tokens: opts.maxTokens ?? 300,
        messages: [
          {
            role: "user",
            content: [
              { type: "text", text: prompt },
              { type: "image_url", image_url: { url: toImageUrl(input) } },
            ],
          },
        ],
      })) as { choices?: Array<{ message?: { content?: string } }> };

      const text = result?.choices?.[0]?.message?.content ?? "";
      return {
        text,
        confidence: 0.9, // chat.completions reports no confidence; neutral default
        structured: { objects: [], dimensions: null, prompt_used: prompt, model },
      };
    } catch (err) {
      if (err instanceof MediaError) throw err;
      throw new MediaError(
        "provider_error",
        `openai-gpt4o-vision caption failed: ${err instanceof Error ? err.message : String(err)}`,
      );
    }
  }
}

const INSTANCE = new OpenaiGpt4oVisionProvider();

/** Self-register so getVisionProvider("openai-gpt4o-vision") works after import. */
export function register(): void {
  registerVisionProvider(INSTANCE);
}
export { INSTANCE as openaiGpt4oVisionProvider };
