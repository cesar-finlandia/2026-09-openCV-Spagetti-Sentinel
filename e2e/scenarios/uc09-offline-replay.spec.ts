// uc09 — a judge with no AWS account still sees it work (REQ-N11).
import { appTest, expect } from "../fixtures/app";
import { startClipRun, waitSummaryAnswering } from "../fixtures/runs";

appTest("uc09 offline replay completes with zero AWS egress", async ({
  page,
  serverURL,
}) => {
  const origins = new Set<string>();
  page.on("request", (req) => {
    try {
      origins.add(new URL(req.url()).hostname);
    } catch {
      origins.add(req.url());
    }
  });

  await page.goto(`${serverURL}/`);
  // Replay is the offline path; the checkbox starts checked.
  await expect(page.getByLabel("Replay (offline)")).toBeChecked();
  const traceId = await startClipRun(page, "good-first-layer", "baseline");
  const events = await waitSummaryAnswering(page, serverURL, traceId);
  expect(events.some((e) => e.step_id === "run-summary")).toBe(true);

  for (const host of origins) {
    expect(
      host === "127.0.0.1" || host === "localhost",
      `unexpected egress to ${host}`,
    ).toBe(true);
  }
});
