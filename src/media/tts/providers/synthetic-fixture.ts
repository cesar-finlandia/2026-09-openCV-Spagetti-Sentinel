// Requirement IDs: MED-04, MED-TTS-01, MED-AC-01, GOV-REU-02, GOV-MIN-04,
// NONGOAL-06
// Always-available offline TTS provider — DP-C §4.4 built-in.
//
// Reads the checked-in synthetic fixture bytes:
//   examples/dummy-fixtures/media/tts/sample.mp3   (~1.1 s synthetic audio)
//   examples/dummy-fixtures/media/tts/sample.wav   (wav variant for format tests)
// and returns them byte-for-byte — NO network, NO credentials. This is what
// MED-AC-01 offline tests rely on. Fixture content is Acme Corp/widget
// synthetic only (GOV-REU-02); the `synthetic` provenance flag is set by the
// wrapper because this provider's id is "synthetic-fixture" (MED-04).
//
// Request/response only: no native synthesizeStream — the wrapper polyfills
// streaming by slicing these bytes (DP-C §5.1).

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { MediaError } from "../../config.js";
import { registerTtsProvider } from "./types.js";
import type { TtsFormat, TtsInput, TtsOptions, TtsProvider, TtsResult } from "./types.js";

function repoRoot(): string {
  // src/media/tts/providers/synthetic-fixture.ts → repo root is ../../../../
  return fileURLToPath(new URL("../../../..", import.meta.url));
}

const FIXTURE_DIR = () => `${repoRoot()}examples/dummy-fixtures/media/tts`;

const FORMAT_FILES: Record<string, string> = {
  mp3: "sample.mp3",
  wav: "sample.wav",
  pcm: "sample.mp3", // raw-tone fixture; served as-is for offline pcm tests
};

/** ~1.1 s of synthetic audio per examples/dummy-fixtures/media/tts/README.md. */
const FIXTURE_DURATION_MS = 1120;
const DEFAULT_SAMPLE_RATE = 24000;

function textOf(input: TtsInput): string {
  return typeof input === "string" ? input : input.text;
}

class SyntheticFixtureTtsProvider implements TtsProvider {
  readonly id = "synthetic-fixture";

  async synthesize(input: TtsInput, opts: TtsOptions): Promise<TtsResult> {
    const format = (opts.format ?? "mp3") as TtsFormat;
    const file = FORMAT_FILES[format];
    if (!file) {
      // Defensive: the wrapper rejects unknown formats before this point.
      throw new MediaError("provider_error", `synthetic-fixture has no fixture for format "${String(opts.format)}"`);
    }
    let audio: Uint8Array;
    try {
      audio = readFileSync(`${FIXTURE_DIR()}/${file}`);
    } catch (err) {
      throw new MediaError(
        "provider_error",
        `synthetic-fixture unreadable (${err instanceof Error ? err.message : String(err)})`,
      );
    }
    void textOf(input); // text echoed by the wrapper; provider ignores content
    return {
      audio,
      format,
      sampleRate: opts.sampleRate ?? DEFAULT_SAMPLE_RATE,
      duration_ms: FIXTURE_DURATION_MS,
      audio_ref: `examples/dummy-fixtures/media/tts/${file}`,
    };
  }
}

const INSTANCE = new SyntheticFixtureTtsProvider();

/** Self-register so getTtsProvider("synthetic-fixture") works after import. */
export function register(): void {
  registerTtsProvider(INSTANCE);
}
export { INSTANCE as syntheticFixtureTtsProvider };
