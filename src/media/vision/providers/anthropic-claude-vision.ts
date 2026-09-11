// Requirement IDs: MED-03, MED-RES-01, MED-REU-01, GOV-MIN-04, GOV-RES-02, XCUT-08
// anthropic-claude-vision provider — DP-C §4.2 built-in (secondary per §6.4).
//
// Optional-dep style (GOV-MIN-04): the `@anthropic-ai/sdk` is required lazily
// on first call; a missing credential throws MediaError("missing_credentials")
// AT CALL TIME so RES-01 can retry/fallback — never a startup crash (§7.3).
// Credential VALUE read via resolveCredential() using only the env var NAME in
// credentials_env (GOV-RES-02 indirection). Generic prompt only (MED-REU-01).

import { readFileSync } from "node:fs";
import { MediaError, resolveCredential } from "../../config.js";
import { defaultPrompt, registerVisionProvider } from "./types.js";
import type { ImageInput, VisionOptions, VisionProvider, VisionResult } from "./types.js";

/** Minimal structural surface of the lazily-required Anthropic client we use. */
interface AnthropicClientLike {
  messages: {
    create(args: Record<string, unknown>): Promise<unknown>;
  };
}

function requireAnthropic(apiKey: string): AnthropicClientLike {
  try {
    const Ctor = requireAnthropicModule();
    return new Ctor({ apiKey }) as AnthropicClientLike;
  } catch (err) {
    throw new MediaError(
      "provider_error",
      `@anthropic-ai/sdk unavailable for provider anthropic-claude-vision (${err instanceof Error ? err.message : String(err)})`,
    );
  }
}

let anthropicCtorCache: (new (opts: { apiKey: string }) => unknown) | null = null;
function requireAnthropicModule(): new (opts: { apiKey: string }) => unknown {
  const cached = anthropicCtorCache;
  if (cached !== null) return cached;
  // eslint-disable-next-line @typescript-eslint/no-require-imports -- optional dep, lazy CJS interop
  const { createRequire } = require("node:module");
  const req = createRequire(import.meta.url);
  const Ctor = (req("@anthropic-ai/sdk").default ?? req("@anthropic-ai/sdk")) as new (
    opts: { apiKey: string },
  ) => unknown;
  anthropicCtorCache = Ctor;
  return Ctor;
}

const MIME_BY_EXT: Record<string, string> = {
  png: "image/png",
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
  webp: "image/webp",
};

interface ImageSource {
  type: "base64" | "url";
  media_type?: string;
  data?: string;
  url?: string;
}

/** Materialize any input variant into an Anthropic image source block:
 * remote urls pass through; path/buffer/base64 become base64 sources. */
function toImageSource(input: ImageInput): ImageSource {
  if ("url" in input) return { type: "url", url: input.url };
  if ("base64" in input) return { type: "base64", media_type: input.mime, data: input.base64 };
  if ("buffer" in input) {
    return {
      type: "base64",
      media_type: input.mime ?? "image/png",
      data: Buffer.from(input.buffer).toString("base64"),
    };
  }
  const ext = (input.path.split(".").pop() ?? "png").toLowerCase();
  return {
    type: "base64",
    media_type: MIME_BY_EXT[ext] ?? "image/png",
    data: readFileSync(input.path).toString("base64"),
  };
}

class AnthropicClaudeVisionProvider implements VisionProvider {
  readonly id = "anthropic-claude-vision";

  async caption(input: ImageInput, opts: VisionOptions): Promise<VisionResult> {
    // Credential first (call-time check, GOV-RES-02/§7.3) — throws MediaError(
    // "missing_credentials") when the named env var is unset.
    const apiKey = resolveCredential({
      provider: this.id,
      credentials_env: opts.credentials_env || "ANTHROPIC_API_KEY",
    });
    const client = requireAnthropic(apiKey);
    const model = opts.model ?? "claude-3-5-sonnet-latest";
    const prompt = opts.prompt ?? defaultPrompt();
    try {
      const result = (await client.messages.create({
        model,
        max_tokens: opts.maxTokens ?? 300,
        messages: [
          {
            role: "user",
            content: [
              { type: "image", source: toImageSource(input) },
              { type: "text", text: prompt },
            ],
          },
        ],
      })) as { content?: Array<{ type: string; text?: string }> };

      const text =
        (result?.content ?? [])
          .filter((block) => block.type === "text")
          .map((block) => block.text ?? "")
          .join("\n") ?? "";
      return {
        text,
        confidence: 0.9, // messages API reports no confidence; neutral default
        structured: { objects: [], dimensions: null, prompt_used: prompt, model },
      };
    } catch (err) {
      if (err instanceof MediaError) throw err;
      throw new MediaError(
        "provider_error",
        `anthropic-claude-vision caption failed: ${err instanceof Error ? err.message : String(err)}`,
      );
    }
  }
}

const INSTANCE = new AnthropicClaudeVisionProvider();

/** Self-register so getVisionProvider("anthropic-claude-vision") works after import. */
export function register(): void {
  registerVisionProvider(INSTANCE);
}
export { INSTANCE as anthropicClaudeVisionProvider };
