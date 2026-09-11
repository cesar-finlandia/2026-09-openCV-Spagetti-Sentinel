// Browser shim for the static `import { randomUUID } from "node:crypto"` used
// by src/platform/transport/publisher.ts. Delegates to WebCrypto.
// Chassis sources are NOT modified.
export function randomUUID(): string {
  const c = (globalThis as unknown as { crypto?: { randomUUID?: () => string } }).crypto;
  if (c?.randomUUID) return c.randomUUID();
  // Fallback for non-secure contexts: 128 random bits hex with v4 layout.
  const b = new Uint8Array(16);
  (globalThis as unknown as { crypto?: { getRandomValues?: (a: Uint8Array) => void } }).crypto?.getRandomValues?.(b);
  b[6] = (b[6]! & 0x0f) | 0x40;
  b[8] = (b[8]! & 0x3f) | 0x80;
  const h = [...b].map((x) => x.toString(16).padStart(2, "0")).join("");
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}
