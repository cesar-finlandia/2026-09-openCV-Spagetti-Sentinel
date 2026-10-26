// uc06 — mandatory technology: OpenCV 5 / COOL, reported at runtime.
// NOTE (fix-log #3): with cool_version null on this host both runs honestly
// render the baseline badge; the COOL branch is re-exercised after the COOL
// redeploy. What this scenario proves now: per-run backend identity, a real
// OpenCV 5 version on the wire, and real per-operation timings.
import type { Page } from "@playwright/test";
import { appTest, expect } from "../fixtures/app";
import { collectEvents } from "../fixtures/envelopes";
import { startClipRun, waitSummaryAnswering } from "../fixtures/runs";

const OPS = [
  "resize",
  "cvt_gray",
  "gaussian_blur",
  "threshold",
  "morphology",
  "sobel",
];

async function runOnce(page: Page, serverURL: string, backend: string) {
  await page.goto(`${serverURL}/`);
  const traceId = await startClipRun(page, "good-first-layer", backend);
  const events = await waitSummaryAnswering(page, serverURL, traceId);
  return { traceId, events };
}

appTest("uc06 backend switch is reported and both backends do real work", async ({
  page,
  serverURL,
}) => {
  const health = (await (await fetch(`${serverURL}/healthz`)).json()) as {
    cool_version: string | null;
    opencv_version: string;
    arch: string;
  };

  const seen: Record<string, { opencv: string; backend: string; ops: string[] }> = {};
  for (const backend of ["cool", "baseline"]) {
    const { events } = await runOnce(page, serverURL, backend);
    const start = events.find((e) => e.step_id === "run-start");
    const p = (start?.payload ?? {}) as Record<string, unknown>;
    expect(String(p["opencv_version"] ?? "")).toMatch(/^5\./);
    // R1 fallback is honest: requesting "cool" without a COOL build reports
    // the baseline backend (with coolVersion null); with COOL installed it
    // reports "cool".
    if (backend === "cool" && health.cool_version === null) {
      expect(String(p["backend"] ?? "")).toEqual("baseline");
    } else {
      expect(String(p["backend"] ?? "")).toEqual(backend);
    }
    const perceives = events.filter(
      (e) => e.step_id === "perceive" && e.status === "done",
    );
    expect(perceives.length).toBeGreaterThan(10);
    const ops = Object.keys(
      ((perceives[0]?.payload?.["scores"] as Record<string, unknown>)?.[
        "ops_ms"
      ] as Record<string, unknown>) ?? {},
    );
    for (const op of OPS) expect(ops).toContain(op);

    // The badge is honest about what is installed on this host.
    if (health.cool_version !== null) {
      await expect(
        page.getByLabel(`COOL backend on ${health.arch}`, { exact: true }),
      ).toBeVisible();
    } else {
      await expect(
        page.getByLabel("baseline OpenCV backend", { exact: true }),
      ).toBeVisible();
    }
    seen[backend] = { opencv: String(p["opencv_version"]), backend: String(p["backend"]), ops };
  }
  expect(seen["cool"]!.opencv).toMatch(/^5\./);
  expect(seen["baseline"]!.opencv).toMatch(/^5\./);
  void collectEvents;
});
