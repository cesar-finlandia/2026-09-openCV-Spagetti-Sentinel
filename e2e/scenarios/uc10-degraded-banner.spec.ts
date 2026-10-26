// uc10 — the system tells the truth when it is degraded: the evidence vault
// is unavailable, the banner names it, and the run still completes.
// NOTE (fix-log #2): no RES_FORCED_DEGRADED mechanism exists in app/api, and
// an undecodable upload completes 0-frame with no degraded envelopes — so the
// user-true trigger is a genuinely unavailable vault (the serverURL fixture
// points SS_EVIDENCE_DIR at a file for this test's title), mirroring eval's
// evidence-store-unavailable case at the UI level.
import { appTest, expect } from "../fixtures/app";
import { startClipRun, waitSummary } from "../fixtures/runs";

appTest("uc10 a dead evidence vault degrades honestly and still completes", async ({
  page,
  serverURL,
}) => {
  await page.goto(`${serverURL}/`);
  // Real pipeline (evidence only materialises off replay — fix-log #12).
  await page.getByLabel("Replay (offline)").uncheck();
  const traceId = await startClipRun(page, "stringing", "baseline");

  // The run still completes with the vault dead (backend truth first: the
  // banner only appears once degraded evidence flows mid-run, and the banner
  // persists — assert it after, with a short timeout).
  const events = await waitSummary(page, serverURL, traceId, 110_000);
  expect(events.some((e) => e.step_id === "run-summary")).toBe(true);

  // The banner names at least one reason; no unhandled error (console gate).
  const banner = page.getByText(/^Running degraded:/);
  await expect(banner.first()).toBeVisible({ timeout: 15_000 });
  expect(
    (await banner.innerText()).replace(/^Running degraded:\s*/, "").length,
  ).toBeGreaterThan(0);
});
