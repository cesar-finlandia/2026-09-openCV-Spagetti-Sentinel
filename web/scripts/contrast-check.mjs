// Contrast gate for DP-UI WU-UI-02: asserts every pairing named in §5.2's
// "Contrast, measured" paragraph meets WCAG AA in both themes.
// Prints `contrast: {n} pairs OK` (n is 42 for the token set) or exits 1.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const cssPath = join(dirname(fileURLToPath(import.meta.url)), "..", "src", "theme.css");
const css = readFileSync(cssPath, "utf8");

function block(selector) {
  const m = css.match(new RegExp(selector.replace(/[[\]"]/g, "\\$&") + "\\s*\\{([\\s\\S]*?)\\}"));
  if (!m) throw new Error(`contrast-check: block not found: ${selector}`);
  return m[1];
}

function vars(text) {
  const out = {};
  for (const m of text.matchAll(/(--[a-z0-9-]+)\s*:\s*([^;]+);/g)) {
    out[m[1]] = m[2].trim();
  }
  return out;
}

function resolve(tokens, name, depth = 0) {
  if (depth > 5) throw new Error(`contrast-check: var cycle at ${name}`);
  const v = tokens[name];
  if (!v) throw new Error(`contrast-check: unknown token ${name}`);
  const m = v.match(/^var\((--[a-z0-9-]+)\)$/);
  return m ? resolve(tokens, m[1], depth + 1) : v;
}

function lum(hex) {
  const m = hex.match(/^#([0-9A-Fa-f]{6})$/);
  if (!m) throw new Error(`contrast-check: not a hex colour: ${hex}`);
  const c = [0, 2, 4].map((i) => {
    const s = parseInt(m[1].slice(i, i + 2), 16) / 255;
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
}

function ratio(a, b) {
  const l1 = lum(a);
  const l2 = lum(b);
  const [hi, lo] = l1 >= l2 ? [l1, l2] : [l2, l1];
  return (hi + 0.05) / (lo + 0.05);
}

const themes = { light: vars(block(":root")), dark: vars(block('[data-theme="dark"]')) };

// [foreground, background, minimum] — the §5.2 pairings.
const AA = [
  ["--text", "--bg", 4.5], ["--text-muted", "--bg", 4.5],
  ["--accent-text", "--bg", 4.5], ["--warning-text", "--bg", 4.5],
  ["--danger", "--bg", 4.5], ["--degraded-text", "--bg", 4.5],
  ["--text", "--bg-elevated", 4.5], ["--text-muted", "--bg-elevated", 4.5],
  ["--accent-text", "--bg-elevated", 4.5], ["--warning-text", "--bg-elevated", 4.5],
  ["--danger", "--bg-elevated", 4.5], ["--degraded-text", "--bg-elevated", 4.5],
  ["--border-strong", "--bg", 3.0],
  ["--chart-1", "--bg", 3.0], ["--chart-2", "--bg", 3.0],
  ["--chart-3", "--bg", 3.0], ["--chart-4", "--bg", 3.0],
  ["--chart-5", "--bg", 3.0], ["--chart-6", "--bg", 3.0],
  ["--accent-contrast", "--accent", 4.5],
  ["--text", "--bg-alert", 4.5],
];

let ok = 0;
const failures = [];
for (const [theme, tokens] of Object.entries(themes)) {
  for (const [fg, bg, min] of AA) {
    const r = ratio(resolve(tokens, fg), resolve(tokens, bg));
    if (r >= min) {
      ok += 1;
    } else {
      failures.push(`${theme}: ${fg} on ${bg} = ${r.toFixed(2)} (needs ${min})`);
    }
  }
}

if (failures.length > 0) {
  for (const f of failures) console.error(`contrast FAIL: ${f}`);
  process.exit(1);
}
console.log(`contrast: ${ok} pairs OK`);
