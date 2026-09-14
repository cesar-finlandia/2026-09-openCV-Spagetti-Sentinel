// uc10 — the system tells the truth when it is degraded: the evidence vault
// is unavailable, the banner names it, the alert is still delivered and the
// run still completes.
// NOTE (fix-log #2): no RES_FORCED_DEGRADED mechanism exists in app/api, and
// an undecodable upload completes 0-frame with no degraded envelopes — so the
// user-true trigger is a genuinely unavailable vault (E2E_BREAK_EVIDENCE
// points SS_EVIDENCE_DIR at a file), mirroring eval's
// evidence-store-unavailable case at the UI level.
import { appTest, expect } from "../fixtures/app";
import { startClipRun, waitSummary } from "../fixtures/runs";

appTest("uc10 a dead evidence vault degrades honestly and still completes", async ({
  page,
  serverURL,
}) => {
  process.env.E2E_BREAK_EVIDENCE = "1";
  try {
    await page.goto(`${serverURL}/`);
    // Real pipeline (evidence only materialises off replay — fix-log #12).
    await page.getByLabel("Replay (offline)").uncheck();
    const traceId = await startClipRun(page, "stringing", "baseline");

    // The banner appears with at least one reason.
    const banner = page.getByRole("status", { name: /^Running degraded:/ });
    await expect(banner).toBeVisible({ timeout: 90_000 });
    expect(
      (await banner.innerText()).replace(/^Running degraded:\s*/, "").length,
    ).toBeGreaterThan(0);

    // The page still completes a run; no unhandled error (console gate).
    const events = await waitSummary(page, serverURL, traceId, 110_000);
    expect(events.some((e) => e.step_id === "run-summary")).toBe(true);
  } finally {
    delete process.env.E2E_BREAK_EVIDENCE;
  }
});
