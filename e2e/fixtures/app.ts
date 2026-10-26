// Shared Playwright fixture: boots the real server per worker (or honours
// BASE_URL), exposes baseURL, and enforces the console-error gate on every
// scenario via the auto consoleGate fixture.
import { spawn, type ChildProcess } from "node:child_process";
import * as net from "node:net";
import * as path from "node:path";
import { test as base, expect } from "@playwright/test";

type AppFixtures = {
  serverURL: string;
  consoleErrors: string[];
};

function freePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const s = net.createServer();
    s.on("error", reject);
    s.listen(0, "127.0.0.1", () => {
      const addr = s.address();
      s.close(() => resolve(typeof addr === "object" && addr ? addr.port : 0));
    });
  });
}

async function waitHealthy(url: string, timeoutMs: number): Promise<string> {
  const start = Date.now();
  let last = "<no response>";
  while (Date.now() - start < timeoutMs) {
    try {
      const res = await fetch(`${url}/healthz`);
      last = await res.text();
      if (res.ok) return last;
    } catch (e) {
      last = String(e);
    }
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error(`server never became healthy at ${url}: ${last}`);
}

const repoRoot = process.cwd();

export const appTest = base.extend<AppFixtures>({
  serverURL: [
    async ({}, use, testInfo) => {
      const external = process.env.BASE_URL;
      if (external) {
        await use(external.replace(/\/$/, ""));
        return;
      }
      // Test scope (not worker): a fresh server per test gives full
      // isolation (no 409 cascades from a previous test's run). uc10 opts
      // into a broken evidence vault by test title (fixture params resolve
      // before the test body runs, so a body-set env var would arrive late).
      const breakEvidence = /dead evidence vault/.test(
        testInfo.titlePath.join(" "),
      );
      const port = await freePort();
      const url = `http://127.0.0.1:${port}`;
      const marker = `e2e-${new Date().toISOString().replace(/[:.]/g, "-")}`;
      let evidenceDir = path.join(repoRoot, ".e2e-evidence");
      if (breakEvidence) {
        evidenceDir = path.join(repoRoot, ".e2e-evidence-block");
        const { writeFileSync } = await import("node:fs");
        writeFileSync(evidenceDir, "not a directory");
      }
      const env = {
        ...process.env,
        S3_BUCKET: "",
        SS_EVIDENCE_DIR: evidenceDir,
        BUILD_MARKER: marker,
        PYTHONUNBUFFERED: "1",
      };
      const child: ChildProcess = spawn(
        "python",
        ["-m", "uvicorn", "app.api.main:app", "--port", String(port)],
        { cwd: repoRoot, env, stdio: "pipe" },
      );
      let stderr = "";
      child.stderr?.on("data", (d) => {
        stderr += d.toString();
      });
      try {
        await waitHealthy(url, 60_000);
        await use(url);
      } finally {
        child.kill();
        const { rmSync } = await import("node:fs");
        for (const p of [
          path.join(repoRoot, ".e2e-evidence"),
          path.join(repoRoot, ".e2e-evidence-block"),
        ]) {
          try {
            rmSync(p, { recursive: true, force: true });
          } catch {
            /* best effort */
          }
        }
        if ((child.exitCode ?? 0) !== 0 && (child.signalCode ?? "SIGTERM") !== "SIGTERM") {
          // Surface server crashes; teardown still completed.
          throw new Error(`e2e server exited unexpectedly: ${stderr.slice(-2000)}`);
        }
      }
    },
    { scope: "test" },
  ],

  consoleErrors: [
    async ({}, use, testInfo) => {
      const errors: string[] = [];
      await use(errors);
      void testInfo;
    },
    { scope: "test", auto: false },
  ],

  page: async ({ page, consoleErrors }, use, testInfo) => {
    const onConsole = (msg: { type: () => string; text: () => string }) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    };
    const onPageError = (err: Error) => {
      consoleErrors.push(`pageerror: ${err.message}`);
    };
    page.on("console", onConsole);
    page.on("pageerror", onPageError);
    await page.addInitScript(() => {
      if (window.localStorage.getItem("ss-theme") === null) {
        window.localStorage.setItem("ss-theme", "light");
      }
    });
    await use(page);
    page.off("console", onConsole);
    page.off("pageerror", onPageError);
    const title = testInfo.titlePath.join(" ");
    const allowed: RegExp[] = [
      /ResizeObserver loop completed with undelivered notifications/,
    ];
    if (/uc07/.test(title)) {
      // uc07 deliberately requests a missing evidence key (404) and aborts
      // every evidence file route (net::ERR_FAILED) to prove both honest
      // failure paths.
      allowed.push(/Failed to load resource: .*\/api\/evidence\/.*404/);
      allowed.push(/Failed to load resource: net::ERR_FAILED/);
    }
    if (/uc11/.test(title)) {
      // uc11 deliberately kills /events/stream (twice, then always): the
      // browser logs net::ERR_FAILED for each killed stream request.
      allowed.push(/Failed to load resource: net::ERR_FAILED/);
    }
    const unexpected = consoleErrors.filter(
      (t) => !allowed.some((re) => re.test(t)),
    );
    expect(
      unexpected,
      `unexpected console errors:\n${unexpected.join("\n")}`,
    ).toEqual([]);
  },
});

export { expect };
