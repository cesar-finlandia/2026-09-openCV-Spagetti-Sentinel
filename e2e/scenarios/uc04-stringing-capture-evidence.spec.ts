// uc04 — a warning is recorded without waking Maya.
import { appTest, expect } from "../fixtures/app";
import { startClipRun, waitSummaryAnswering } from "../fixtures/runs";

appTest("uc04 stringing captures evidence but never requests a pause", async ({
  page,
  serverURL,
}) => {
  await page.goto(`${serverURL}/`);
  // Evidence only materialises off replay (replay has no frames to clip —
  // fix-log #12), so this use case runs the real pipeline.
  await page.getByLabel("Replay (offline)").uncheck();
  const traceId = await startClipRun(page, "stringing", "baseline");
  const events = await waitSummaryAnswering(page, serverURL, traceId);

  const actions = events
    .filter((e) => e.step_id === "decide" && e.status === "done")
    .map((e) => String((e.payload?.["decision"] as Record<string, unknown>)["action"]));
  expect(actions.filter((a) => a === "capture_evidence").length).toBeGreaterThan(0);
  expect(actions.filter((a) => a === "request_pause_approval")).toHaveLength(0);
  await expect(page.getByRole("alertdialog")).toHaveCount(0);

  // The evidence panel gains playable items (backend proof above + rendering).
  const evidence = page.getByRole("region", { name: "Evidence" }).or(
    page.locator('section[aria-label="Evidence"]'),
  );
  await expect(evidence.locator(".evidence-item").first()).toBeVisible({
    timeout: 15_000,
  });
});
