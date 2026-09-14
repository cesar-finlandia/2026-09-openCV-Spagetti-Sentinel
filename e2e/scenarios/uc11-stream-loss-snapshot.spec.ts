// uc11 — a judge on bad Wi-Fi loses nothing: the stream dies twice, the
// client downgrades to the GET /events snapshot, and the trace still fills.
// Mechanism: abort every /events/stream attempt (first failure + the one
// auto-retry), while holding the client's fallback GET /events until the
// run completes server-side — so the snapshot it serves is the completed
// run, exactly what the plan's assertions require.
import { appTest, expect } from "../fixtures/app";
import { collectEvents } from "../fixtures/envelopes";
import { startClipRun } from "../fixtures/runs";

appTest("uc11 stream loss falls back to the completed-run snapshot", async ({
  page,
  serverURL,
}) => {
  let releaseFallback: (() => void) | null = null;
  const fallbackHeld = new Promise<void>((resolve) => {
    releaseFallback = resolve;
  });
  await page.route("**/events/stream*", (route) => route.abort());
  await page.route("**/events?trace_id=*", async (route) => {
    if (route.request().method() === "GET") {
      await fallbackHeld;
    }
    await route.continue();
  });

  await page.goto(`${serverURL}/`);
  const traceId = await startClipRun(page, "good-first-layer", "baseline");

  // Backend truth first: the run completes unaffected by the dead stream.
  const backend = await (async () => {
    const start = Date.now();
    while (Date.now() - start < 110_000) {
      const events = await collectEvents(serverURL, traceId);
      if (events.some((e) => e.step_id === "run-summary")) return events;
      await page.waitForTimeout(1000);
    }
    throw new Error("run never completed server-side");
  })();
  const decideCount = backend.filter(
    (e) => e.step_id === "decide" && e.status === "done",
  ).length;
  expect(decideCount).toBeGreaterThan(0);

  // Release the snapshot; the pill must read snapshot mode and the trace
  // must fill from GET /events with the backend's full row count.
  releaseFallback!();
  await expect(
    page.getByText("snapshot mode — showing the completed run"),
  ).toBeVisible({ timeout: 30_000 });
  const table = page.getByRole("table");
  await expect(table.getByRole("row")).not.toHaveCount(0, { timeout: 30_000 });
  expect(await table.getByRole("row").count()).toEqual(decideCount + 1); // + header
});
