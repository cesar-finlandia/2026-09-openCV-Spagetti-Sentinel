// Requirement IDs: MED-04, MED-AC-01, MED-REU-01, GOV-REU-02, GOV-MIN-04, NONGOAL-06
// Always-available offline vision provider — DP-C §4.2 built-ins.
//
// Reads the checked-in synthetic fixture pair:
//   examples/dummy-fixtures/media/vision/sample.png   (640x480 synthetic scene)
//   examples/dummy-fixtures/media/vision/caption.json (expected output)
// and returns caption.json verbatim — NO network, NO credentials. This is
// what MED-AC-01 offline tests rely on. Fixture content is Acme Corp/widget
// synthetic only (GOV-REU-02); the `synthetic` provenance flag is set by the
// wrapper because this provider's id is "synthetic-fixture" (MED-04).

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { registerVisionProvider } from "./types.js";
import type { ImageInput, VisionOptions, VisionProvider, VisionResult } from "./types.js";

interface CaptionFixture {
  text: string;
  objects?: Array<Record<string, unknown>>;
}

function repoRoot(): string {
  // src/media/vision/providers/synthetic-fixture.ts → repo root is ../../../../
  return fileURLToPath(new URL("../../../..", import.meta.url));
}

const CAPTION_PATH = () =>
  `${repoRoot()}examples/dummy-fixtures/media/vision/caption.json`;

let cache: CaptionFixture | null = null;

function loadCaption(): CaptionFixture {
  return (cache ??= JSON.parse(readFileSync(CAPTION_PATH(), "utf8")) as CaptionFixture);
}

function isPng(bytes: Uint8Array): boolean {
  return (
    bytes.byteLength >= 8 &&
    bytes[0] === 0x89 && bytes[1] === 0x50 && bytes[2] === 0x4e && bytes[3] === 0x47 &&
    bytes[4] === 0x0d && bytes[5] === 0x0a && bytes[6] === 0x1a && bytes[7] === 0x0a
  );
}

function isJpeg(bytes: Uint8Array): boolean {
  return (
    bytes.byteLength >= 3 &&
    bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff
  );
}

/** Touch fixture image bytes so a missing/corrupt checked-in file surfaces as
 * a provider error instead of silently returning canned text. */
function assertFixtureImage(input: ImageInput): void {
  if (!("path" in input)) return;
  const img = readFileSync(input.path);
  if (!isPng(img) && !isJpeg(img)) {
    throw new Error(`fixture ${input.path} is not a PNG/JPEG image`);
  }
}

class SyntheticFixtureVisionProvider implements VisionProvider {
  readonly id = "synthetic-fixture";

  async caption(input: ImageInput, _opts: VisionOptions): Promise<VisionResult> {
    assertFixtureImage(input);
    const c = loadCaption();
    return {
      text: c.text,
      confidence: 0.92,
      structured: {
        objects: Array.isArray(c.objects) ? c.objects : [],
        dimensions: { width: 640, height: 480 },
        model: "synthetic-fixture",
      },
    };
  }
}

const INSTANCE = new SyntheticFixtureVisionProvider();

/** Self-register so getVisionProvider("synthetic-fixture") works after import. */
export function register(): void {
  registerVisionProvider(INSTANCE);
}
export { INSTANCE as syntheticFixtureVisionProvider };
