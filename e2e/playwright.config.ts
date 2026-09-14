import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: ".",
  testMatch: ["scenarios/**/*.spec.ts", "smoke.spec.ts"],
  use: {
    browserName: "chromium",
    viewport: { width: 1440, height: 900 },
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  outputDir: "./artifacts",
  retries: 0,
  workers: 1, // the app holds one active run at a time (HTTP 409 for a second)
  reporter: [["list"]],
  timeout: 120_000,
});
