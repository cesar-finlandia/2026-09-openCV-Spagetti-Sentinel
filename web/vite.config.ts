import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";

const repoRoot = fileURLToPath(new URL("..", import.meta.url));
const webSrc = fileURLToPath(new URL("./src/", import.meta.url));

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      src: `${repoRoot}src`,
      // Browser shims for the static node: imports in the chassis transport
      // graph (DP-UI §9 risk 1). The chassis sources are NOT modified; the fs
      // shim serves the real EventEnvelope schema (TRN-06), and ajv at runtime
      // is provided by web/src/node-polyfills.ts via process.getBuiltinModule.
      "node:fs": `${webSrc}shims/node-fs.ts`,
      "node:crypto": `${webSrc}shims/node-crypto.ts`,
    },
  },
  server: {
    proxy: {
      "/api": "http://localhost:8000",
      "/events": "http://localhost:8000",
      "/healthz": "http://localhost:8000",
    },
  },
  build: { outDir: "dist", emptyOutDir: true },
});
