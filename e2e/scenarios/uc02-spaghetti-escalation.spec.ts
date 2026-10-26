// uc02 — the print fails and Maya is asked to approve a pause.
import { appTest, expect } from "../fixtures/app";
import { collectEvents } from "../fixtures/envelopes";
import { drainApprovals, startClipRun } from "../fixtures/runs";

appTest("uc02 spaghetti run escalates to a human pause approval", async ({
  page,
  serverURL,
}) => {
  await page.goto(`${serverURL}/`);
  const traceId = await startClipRun(page, "spaghetti", "baseline");

  // The work indicator proves the app is really working, not just painted.
  await expect(
    page.getByTestId("work-indicator-text"),
  ).not.toBeEmpty({ timeout: 30_000 });

  const dialog = page.getByRole("alertdialog");
  await expect(dialog).toBeVisible({ timeout: 90_000 });
  const sentence = await dialog.innerText();
  const m = sentence.match(/scored (\d+\.\d+)\s+against a threshold of (\d+\.\d+)/);
  expect(m, `dialog sentence quotes score and threshold: ${sentence}`).not.toBeNull();
  expect(Number(m![1])).toBeGreaterThanOrEqual(Number(m![2]));

  await page.getByRole("button", { name: "Approve pause" }).click();
  // The approval resolves as approved:true on the backend …
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
  expect(resolved!.approved).toBe(true);
  // … and the panel unmounts.
  await expect(page.getByRole("alertdialog")).toHaveCount(0, { timeout: 15_000 });

  // Drain the remaining prompts over HTTP, then the run must complete and the
  // alert row must be highlighted in the trace.
  const events = await drainApprovals(serverURL, traceId, traceId, true);
  expect(events.some((e) => e.step_id === "run-summary")).toBe(true);
  const alertRows = page.locator("tr.row-alert");
  expect(await alertRows.count()).toBeGreaterThan(0);
  await expect(alertRows.first()).toContainText("request_pause_approval");
});
