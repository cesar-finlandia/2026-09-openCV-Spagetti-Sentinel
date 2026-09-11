// Browser polyfill for the DYNAMIC Node-builtin path
// (src/resilience/node-compat.ts → process.getBuiltinModule).
//
// The chassis resilience/validate.ts loads ajv via createRequire at first use.
// In a browser there is no createRequire, so validation — which the transport
// subscriber and fallback run on EVERY envelope — would throw and the stream
// would never render. This module installs a minimal process.getBuiltinModule
// that serves the bundled ajv (same validator, same schemas) plus the fs and
// crypto shims, mirroring what Node would resolve. Chassis sources are NOT
// modified; in a real Node runtime (vitest) this module is a no-op.
import Ajv2020 from "ajv/dist/2020";
import addFormats from "ajv-formats";
import { randomUUID } from "./shims/node-crypto";
import { readFileSync } from "./shims/node-fs";

function requireShim(id: string): unknown {
  if (id.includes("ajv/dist/2020")) return Ajv2020;
  if (id.includes("ajv-formats")) return addFormats;
  throw new Error(`browser require() is unavailable for "${id}"`);
}

const moduleShim = {
  createRequire: (_parent: string) => requireShim,
};

const fsShim = { readFileSync };
const cryptoShim = { randomUUID };

const TABLE: Record<string, unknown> = {
  "node:fs": fsShim,
  "node:crypto": cryptoShim,
  "node:module": moduleShim,
};

export function installNodePolyfills(): void {
  const g = globalThis as unknown as {
    process?: { getBuiltinModule?: (id: string) => unknown };
  };
  if (g.process?.getBuiltinModule) return; // real Node — leave alone
  const prev = g.process ?? {};
  g.process = {
    ...prev,
    getBuiltinModule: (id: string) => TABLE[id] ?? null,
  } as NonNullable<typeof g.process>;
}

installNodePolyfills();
