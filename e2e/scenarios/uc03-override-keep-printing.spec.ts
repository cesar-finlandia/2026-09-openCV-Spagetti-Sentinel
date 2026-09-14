// uc03 — Maya disagrees and keeps printing.
import { appTest, expect } from "../fixtures/app";
import { collectEvents } from "../fixtures/envelopes";
import { drainApprovals, startClipRun } from "../fixtures/runs";

appTest("uc03 override keeps printing and claims no pause", async ({
  page,
  serverURL,
}) => {
  await page.goto(`${serverURL}/`);
  const traceId = await startClipRun(page, "spaghetti", "baseline");

  const dialog = page.getByRole("alertdialog");
  await expect(dialog).toBeVisible({ timeout: 90_000 });
  await page.getByRole("button", { name: "Keep printing" }).click();

  const start = Date.now();
  let resolved: { approved: boolean } | null = null;
  while (Date.now() - start < 30_000) {
    const events = await collectEvents(serverURL, traceId);
    const hit = events.filter((e) => e.step_id === "approval-resolved").pop();
    if (hit) {
      resolved = hit.payload as unknown as { approved: boolean };
      break;
    }
    await page.waitForTimeout(500);
  }
  expect(resolved, "an approval-resolved envelope exists").not.toBeNull();
  expect(resolved!.approved).toBe(false);

  const events = await drainApprovals(serverURL, traceId, traceId, true);
  expect(events.some((e) => e.step_id === "run-summary")).toBe(true);

  // Nothing on screen may claim the printer was paused: the system only
  // recommends, the human's override stands.
  const body = await page.locator("body").innerText();
  expect(body).not.toMatch(/printer (was|is|has been) paused/i);
});
