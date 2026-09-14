// uc01 — Maya watches a healthy print and is not disturbed.
import { appTest, expect } from "../fixtures/app";
import { collectEvents } from "../fixtures/envelopes";
import { startClipRun, waitSummaryAnswering } from "../fixtures/runs";

appTest("uc01 nominal run never disturbs the operator", async ({
  page,
  serverURL,
}) => {
  await page.goto(`${serverURL}/`);
  const traceId = await startClipRun(page, "good-first-layer", "baseline");
  const events = await waitSummaryAnswering(page, serverURL, traceId);

  // No approval dialog ever appeared.
  await expect(page.getByRole("alertdialog")).toHaveCount(0);

  // Backend truth: every decision is continue, scores stay below threshold.
  const decides = events.filter(
    (e) => e.step_id === "decide" && e.status === "done",
  );
  expect(decides.length).toBeGreaterThan(10);
  let threshold = 0.72;
  for (const e of decides) {
    const d = e.payload?.["decision"] as Record<string, unknown>;
    expect(String(d["action"])).toEqual("continue");
    threshold = Number(d["threshold"] ?? threshold);
  }
  const perceives = events.filter(
    (e) => e.step_id === "perceive" && e.status === "done",
  );
  const last = perceives[perceives.length - 1]?.payload?.["scores"] as Record<
    string,
    unknown
  >;
  expect(Number(last["spaghetti_score"])).toBeLessThan(threshold);

  // The screen shows what the engine measured: the tile equals the last score.
  const tiles = page.locator(".score-tiles");
  await expect(
    tiles.getByText("Spaghetti score", { exact: true }),
  ).toBeVisible();
  await expect(
    tiles.getByText(Number(last["spaghetti_score"]).toFixed(2), { exact: true }),
  ).toBeVisible();

  // Trace rows all read continue.
  const trace = page.getByRole("table");
  await expect(trace.getByRole("row")).not.toHaveCount(0);
  const actions = await trace.getByRole("row").allInnerTexts();
  for (const row of actions.slice(1)) {
    expect(row).toMatch(/continue/);
  }
  void collectEvents;
});
