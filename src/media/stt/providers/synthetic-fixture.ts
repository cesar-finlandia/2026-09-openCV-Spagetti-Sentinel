// Requirement IDs: MED-04, MED-AC-01, GOV-REU-02, GOV-MIN-04, NONGOAL-06
// Always-available offline STT provider — DP-C §4.1 built-ins.
//
// Reads the checked-in synthetic fixture pair:
//   examples/dummy-fixtures/media/stt/sample.wav   (RIFF/WAVE PCM16, 1.84 s)
//   examples/dummy-fixtures/media/stt/transcript.json (expected output)
// and returns transcript.json verbatim — NO network, NO credentials. This is
// what MED-AC-01 offline tests rely on. Fixture content is Acme Corp/widget
// synthetic only (GOV-REU-02); provenance marker `synthetic` is set by the
// wrapper because the provider id is "synthetic-fixture" (MED-04/NONGOAL-06).

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { registerSttProvider } from "./types.js";
import type { AudioInput, SttOptions, SttProvider, SttResult } from "./types.js";

interface TranscriptFixture {
  text: string;
  language: string;
  duration_ms: number;
  words?: Array<Record<string, unknown>>;
}

function repoRoot(): string {
  // src/media/stt/providers/synthetic-fixture.ts → repo root is ../../../../
  return fileURLToPath(new URL("../../../..", import.meta.url));
}

const TRANSCRIPT_PATH = () =>
  `${repoRoot()}examples/dummy-fixtures/media/stt/transcript.json`;

let cache: TranscriptFixture | null = null;

function loadTranscript(): TranscriptFixture {
  return (cache ??= JSON.parse(readFileSync(TRANSCRIPT_PATH(), "utf8")) as TranscriptFixture);
}

class SyntheticFixtureSttProvider implements SttProvider {
  readonly id = "synthetic-fixture";

  async transcribe(input: AudioInput, _opts: SttOptions): Promise<SttResult> {
    // Touch the fixture audio so a missing/corrupt checked-in file surfaces as
    // a provider error instead of silently returning canned text.
    if ("path" in input) {
      const wav = readFileSync(input.path);
      const header = wav.subarray(0, 12);
      const riff = Buffer.from("RIFF");
      const wave = Buffer.from("WAVE");
      if (
        header.length < 12 ||
        !header.subarray(0, 4).equals(riff) ||
        !header.subarray(8, 12).equals(wave)
      ) {
        throw new Error(`fixture ${input.path} is not a RIFF/WAVE file`);
      }
    }
    const t = loadTranscript();
    return {
      text: t.text,
      confidence: 0.94,
      structured: {
        language: t.language,
        duration_ms: t.duration_ms,
        ...(Array.isArray(t.words) ? { words: t.words } : {}),
      },
    };
  }

  /** Sync twin used only via transcribeSync() (DP-C §4.1 optional surface). */
  transcribeSync(input: AudioInput): SttResult {
    if ("path" in input) {
      const wav = readFileSync(input.path);
      const header = wav.subarray(0, 12);
      const riff = Buffer.from("RIFF");
      const wave = Buffer.from("WAVE");
      if (
        header.length < 12 ||
        !header.subarray(0, 4).equals(riff) ||
        !header.subarray(8, 12).equals(wave)
      ) {
        throw new Error(`fixture ${input.path} is not a RIFF/WAVE file`);
      }
    }
    const t = loadTranscript();
    return {
      text: t.text,
      confidence: 0.94,
      structured: {
        language: t.language,
        duration_ms: t.duration_ms,
        ...(Array.isArray(t.words) ? { words: t.words } : {}),
      },
    };
  }
}

const INSTANCE = new SyntheticFixtureSttProvider();

/** Self-register so getSttProvider("synthetic-fixture") works after import. */
export function register(): void {
  registerSttProvider(INSTANCE);
}
export { INSTANCE as syntheticFixtureProvider };
