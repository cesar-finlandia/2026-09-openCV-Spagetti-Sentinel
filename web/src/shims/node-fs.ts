// Browser shim for the static `import { readFileSync } from "node:fs"` used by
// src/platform/transport/{subscriber,fallback,publisher}.ts.
//
// Those modules read exactly one file at runtime: the EventEnvelope schema
// (TRN-06 single source of truth). Vite inlines that JSON file as a base64
// data: URL inside `new URL(...)`, so at runtime readFileSync receives either
// a path containing the schema filename or the data URL itself. Both are
// served from the real contracts file (imported below, so it cannot drift).
// Anything else throws. Chassis sources are NOT modified.
import envelopeSchema from "../../../contracts/event-envelope.schema.json";

const BUNDLED = JSON.stringify(envelopeSchema);

function keyOf(path: unknown): string {
  if (typeof path === "string") return path;
  try {
    const p = path as { url?: unknown; pathname?: unknown; href?: unknown };
    if (typeof p.href === "string") return p.href;
    if (typeof p.url === "string") return p.url;
    if (typeof p.pathname === "string") return p.pathname;
    return String(path);
  } catch {
    return "";
  }
}

function decodeDataUrl(key: string): string | null {
  const marker = "base64,";
  const i = key.indexOf(marker);
  if (i < 0) return null;
  try {
    const raw = key.slice(i + marker.length).replace(/\s+/g, "");
    const bin = atob(raw);
    const bytes = Uint8Array.from(bin, (c) => c.charCodeAt(0));
    const text = new TextDecoder().decode(bytes);
    const parsed = JSON.parse(text) as { title?: unknown; $id?: unknown };
    if (parsed && (parsed.title === "EventEnvelope" || String(parsed.$id ?? "").includes("event-envelope"))) {
      return JSON.stringify(parsed);
    }
    return text;
  } catch {
    return null;
  }
}

export function readFileSync(path: unknown, _options?: unknown): string {
  const key = keyOf(path).replace(/\\/g, "/");
  if (key.includes("event-envelope.schema.json")) {
    return BUNDLED;
  }
  const decoded = decodeDataUrl(key);
  if (decoded !== null) return decoded;
  throw new Error(
    `node:fs readFileSync is unavailable in the browser (requested: ${key.slice(0, 120)})`,
  );
}

export function existsSync(_path: unknown): boolean {
  return false;
}
