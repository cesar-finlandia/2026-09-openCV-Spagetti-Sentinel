#!/usr/bin/env node
// DP-UI-V2 §8 — emit cinematic-tokens.json FROM theme.css, never by hand.
// The video's scenes, the generated plates' style block and the end card all
// import this file. A colour in a video layer that is not here is a defect.
//
//   node web/scripts/emit-cinematic-tokens.mjs [outPath]
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const cssPath = join(here, "..", "src", "theme.css");
const out =
  process.argv[2] ??
  resolve(here, "..", "..", "..", "..", "hackathons", "hackathon-projects",
          "2026-09-openCV", "cinematic-tokens.json");

const css = readFileSync(cssPath, "utf8");
const root = css.slice(css.indexOf(":root {"), css.indexOf("[data-theme=\"light\"]"));

const vars = new Map();
for (const m of root.matchAll(/--([a-z0-9-]+)\s*:\s*([^;]+);/gi)) {
  vars.set(m[1], m[2].trim());
}
const v = (name) => {
  const raw = vars.get(name);
  if (raw === undefined) throw new Error(`theme.css :root is missing --${name}`);
  const ref = /^var\(--([a-z0-9-]+)\)$/i.exec(raw);
  return ref ? v(ref[1]) : raw;
};
const hex = (name) => {
  const val = v(name);
  if (!/^#[0-9a-f]{6}$/i.test(val)) throw new Error(`--${name} is not a six-digit hex: ${val}`);
  return val.toUpperCase();
};
const px = (name) => Number.parseInt(v(name), 10);

const tokens = {
  project: "2026-09-openCV",
  theme: "dark",
  source: "web/src/theme.css:root",
  generated_by: "web/scripts/emit-cinematic-tokens.mjs",
  color: {
    bg: hex("bg"), bgElevated: hex("bg-elevated"), bgSunken: hex("bg-sunken"),
    bgAlert: hex("bg-alert"), border: hex("border"), borderStrong: hex("border-strong"),
    text: hex("text"), textMuted: hex("text-muted"), textInverse: hex("text-inverse"),
    accent: hex("accent"), accentHover: hex("accent-hover"), accentContrast: hex("accent-contrast"),
    warning: hex("warning"), danger: hex("danger"), degraded: hex("degraded"),
    chart: [1, 2, 3, 4, 5, 6].map((i) => hex(`chart-${i}`)),
  },
  font: {
    display: "Space Grotesk",
    text: "Inter",
    mono: "JetBrains Mono",
  },
  radius: { sm: px("r-sm"), md: px("r-md"), lg: px("r-lg"), pill: px("r-pill") },
  space: [1, 2, 3, 4, 5, 6, 7, 8].map((i) => px(`sp-${i}`)),
  motion: {
    fast: px("motion-fast"), base: px("motion-base"), slow: px("motion-slow"),
    ease: v("ease"),
  },
  elevation: [1, 2, 3].map((i) => ({
    bg: hex(`elev-${i}-bg`), border: hex(`elev-${i}-border`), shadow: v(`elev-${i}-shadow`),
  })),
  type: {
    hero: 72, display: 48, h1: 34, h2: 26, h3: 20,
    body: 18, small: 16, caption: 16, readoutLg: 44, readout: 28, mono: 16,
  },
};

mkdirSync(dirname(out), { recursive: true });
writeFileSync(out, JSON.stringify(tokens, null, 2) + "\n", "utf8");
console.log(`wrote ${out}`);
