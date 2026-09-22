// DP-UI-V2 §7 — the static half of the craft audit. It reads the real files, so
// it fails the moment someone hard-codes a hex, shrinks a size below the camera
// floor, or reinstates an on-mount animation.
import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = resolve(HERE, "..");
const css = readFileSync(join(SRC, "theme.css"), "utf8");
const html = readFileSync(resolve(SRC, "..", "index.html"), "utf8");

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) {
      if (name !== "__tests__" && name !== "brand") walk(p, out);
    } else if (/\.tsx?$/.test(name)) {
      out.push(p);
    }
  }
  return out;
}

/** ui-craft.spec.md §13.1 — sizes are set for the camera, not for the desk. */
const SCALE: Record<string, number> = {
  hero: 72, display: 48, h1: 34, h2: 26, h3: 20,
  strong: 18, small: 16, caption: 16,
  "readout-lg": 44, readout: 28, mono: 16,
};

describe("craft audit (static)", () => {
  it("every type-scale class is declared at exactly its camera size", () => {
    for (const [cls, size] of Object.entries(SCALE)) {
      const rule = new RegExp(`\\.${cls}\\s*\\{[^}]*font-size:\\s*(\\d+)px`);
      const m = rule.exec(css);
      expect(m, `.${cls} is missing from theme.css`).not.toBeNull();
      expect(Number(m![1]), `.${cls}`).toBe(size);
    }
  });

  it("body is 18px — the camera floor for body text", () => {
    const m = /\bbody\s*\{[^}]*font-size:\s*(\d+)px/.exec(css);
    expect(m).not.toBeNull();
    expect(Number(m![1])).toBeGreaterThanOrEqual(18);
  });

  it("nothing anywhere in the stylesheet is smaller than 16px", () => {
    const sizes = [...css.matchAll(/font-size:\s*(\d+)px/g)].map((m) => Number(m[1]));
    expect(sizes.length).toBeGreaterThan(5);
    expect(Math.min(...sizes)).toBeGreaterThanOrEqual(16);
  });

  it("the hero metric is at least 64px", () => {
    expect(SCALE.hero).toBeGreaterThanOrEqual(64);
  });

  it("no six-digit hex outside theme.css", () => {
    const offenders: string[] = [];
    for (const f of walk(SRC)) {
      const body = readFileSync(f, "utf8");
      if (/#[0-9a-fA-F]{6}\b/.test(body)) offenders.push(f.slice(SRC.length + 1));
    }
    expect(offenders).toEqual([]);
  });

  it("the motion tokens are all inside the 200-400ms legibility window", () => {
    for (const name of ["motion-fast", "motion-base", "motion-slow"]) {
      const m = new RegExp(`--${name}:\\s*(\\d+)ms`).exec(css);
      expect(m, `--${name} missing`).not.toBeNull();
      const ms = Number(m![1]);
      expect(ms).toBeGreaterThanOrEqual(200);
      expect(ms).toBeLessThanOrEqual(400);
    }
  });

  it("nothing animates ambiently or on mount", () => {
    // an infinite animation is ambient motion; .card had an on-mount enter.
    const ambient = [...css.matchAll(/^(?!\s*\/\*).*animation:[^;]*\binfinite\b[^;]*;/gm)]
      .map((m) => m[0].trim())
      // the loading spinner is the one exception: it is never on screen in the
      // quiet frame, which theme.css forbids animations in.
      .filter((line) => !/spinner/.test(line));
    expect(ambient).toEqual([]);
    expect(/\.card\s*\{\s*animation:/.test(css)).toBe(false);
  });

  it("the quiet frame forbids animation", () => {
    expect(css).toMatch(/\[data-quiet="true"\][^{]*\{[^}]*animation:\s*none\s*!important/);
  });

  it("reduced motion is honoured", () => {
    expect(css).toMatch(/@media \(prefers-reduced-motion: reduce\)/);
  });

  it("dark is the default theme, declared before first paint", () => {
    expect(html).toMatch(/<html[^>]*data-theme="dark"/);
    expect(css).toMatch(/:root\s*\{[^}]*color-scheme:\s*dark/);
    expect(css).toMatch(/\[data-theme="light"\]/);
  });

  it("the six demo-focus anchors exist, each exactly once in the source", () => {
    const wanted = ["score", "timeline", "decision", "approval", "evidence", "backend"];
    const bodies = walk(SRC).map((f) => readFileSync(f, "utf8")).join("\n");
    for (const key of wanted) {
      const hits = [...bodies.matchAll(new RegExp(`data-demo-focus="${key}"`, "g"))];
      // BackendBadge declares its anchor on both of its two exclusive branches.
      expect(hits.length, key).toBeGreaterThanOrEqual(1);
      expect(hits.length, key).toBeLessThanOrEqual(2);
    }
  });
});
