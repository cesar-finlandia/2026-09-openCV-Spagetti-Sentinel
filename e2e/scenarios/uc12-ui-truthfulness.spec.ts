// uc12 — the screen does not lie: every rendered cell equals the backend's
// envelopes at displayed precision (scores/confidence 2dp, t integer ms).
import { appTest, expect } from "../fixtures/app";
import { drainApprovals, startClipRun } from "../fixtures/runs";

appTest("uc12 rendered trace, tiles and marker match backend truth", async ({
  page,
  serverURL,
}) => {
  await page.goto(`${serverURL}/`);
  const traceId = await startClipRun(page, "spaghetti", "baseline");
  const events = await drainApprovals(serverURL, traceId, traceId, true);
  expect(events.some((e) => e.step_id === "run-summary")).toBe(true);

  // Expected rows: zip perceive.scores with decide.decision on frame_index.
  const scores = new Map<number, Record<string, unknown>>();
  for (const e of events) {
    if (e.step_id !== "perceive" || e.status !== "done") continue;
    const s = e.payload?.["scores"] as Record<string, unknown>;
    scores.set(Number(s["frame_index"]), s);
  }
  const expected: string[][] = [];
  for (const e of events) {
    if (e.step_id !== "decide" || e.status !== "done") continue;
    const d = e.payload?.["decision"] as Record<string, unknown>;
    const s = scores.get(Number(d["frame_index"]));
    if (!s) continue;
    expected.push([
      String(d["frame_index"]),
      String(Math.round(Number(s["t_ms"]))),
      Number(s["spaghetti_score"]).toFixed(2),
      Number(s["confidence"]).toFixed(2),
      Number(d["threshold"]).toFixed(2),
      String(d["action"]),
      String(d["reason_code"]),
    ]);
  }
  expect(expected.length).toBeGreaterThan(10);

  const table = page.locator('section[aria-label="Decision trace"] table');
  await expect(table.getByRole("row")).not.toHaveCount(0);
  const rendered = await table.getByRole("row").allInnerTexts();
  const body = rendered.slice(1); // skip the header
  expect(body.length).toEqual(expected.length);
  for (let i = 0; i < expected.length; i++) {
    const cells = body[i]!.split("\t");
    // columns: # | t (ms) | frame | spaghetti | confidence | threshold | action | reason | human?
    expect(cells[2]!.trim()).toEqual(expected[i]![0]);
    expect(cells[1]!.trim()).toEqual(expected[i]![1]);
    expect(cells[3]!.trim()).toEqual(expected[i]![2]);
    expect(cells[4]!.trim()).toEqual(expected[i]![3]);
    expect(cells[5]!.trim()).toEqual(expected[i]![4]);
    expect(cells[6]!.trim()).toEqual(expected[i]![5]);
    expect(cells[7]!.trim()).toEqual(expected[i]![6]);
  }

  // The alert row is the one the backend says it is, by frame index.
  const alertFrame = String(
    (events
      .filter((e) => e.step_id === "decide" && e.status === "done")
      .map((e) => e.payload?.["decision"] as Record<string, unknown>)
      .find((d) => d["action"] === "request_pause_approval") ?? {})["frame_index"],
  );
  const alertRow = page.locator("tr.row-alert").first();
  await expect(alertRow).toContainText(alertFrame);

  // The score tile equals the last perceive score; the footer marker equals
  // the live /healthz marker.
  const lastScore = [...scores.values()].pop()!;
  const tiles = page.locator(".score-tiles");
  await expect(
    tiles.getByText(Number(lastScore["spaghetti_score"]).toFixed(2), { exact: true }),
  ).toBeVisible();
  const health = (await (await fetch(`${serverURL}/healthz`)).json()) as {
    build_marker: string;
  };
  await expect(page.getByRole("contentinfo")).toContainText(
    `build ${health.build_marker}`,
  );
});
