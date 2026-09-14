// uc05 — mandatory technology: Agentic Vision. The vision number, not a
// chatbot, changes what the system does.
import { appTest, expect } from "../fixtures/app";
import { drainApprovals, startClipRun } from "../fixtures/runs";

appTest("uc05 vision output changes the action, tools manifest, honest rationale", async ({
  page,
  serverURL,
}) => {
  // Exactly 4 tools with JSON schemas — the artefact of the real registry.
  const toolsRes = await fetch(`${serverURL}/api/tools`);
  expect(toolsRes.ok).toBe(true);
  const tools = (await toolsRes.json()) as {
    name: string;
    input_schema: { type?: string };
  }[];
  expect(Array.isArray(tools)).toBe(true);
  expect(tools).toHaveLength(4);
  const names = tools.map((t) => t.name).sort();
  expect(names).toContain("score_frame");
  for (const t of tools) {
    expect(t.input_schema?.type).toEqual("object");
  }

  await page.goto(`${serverURL}/`);
  const traceId = await startClipRun(page, "spaghetti", "baseline");
  const events = await drainApprovals(serverURL, traceId, traceId, true);

  // The manifest also renders in the UI trace card once the run exists.
  const traceCard = page.locator('section[aria-label="Decision trace"]');
  await expect(traceCard).toBeVisible();
  await expect(traceCard.getByText("Agent tools (4)")).toBeVisible();

  // Score-crosses-threshold ⟺ action flips, on the backend's own envelopes.
  const scores = new Map<number, number>();
  for (const e of events) {
    if (e.step_id !== "perceive" || e.status !== "done") continue;
    const s = e.payload?.["scores"] as Record<string, unknown>;
    scores.set(Number(s["frame_index"]), Number(s["spaghetti_score"]));
  }
  let threshold = 0.72;
  let checked = 0;
  for (const e of events) {
    if (e.step_id !== "decide" || e.status !== "done") continue;
    const d = e.payload?.["decision"] as Record<string, unknown>;
    if (d["degraded"] === true) continue;
    threshold = Number(d["threshold"] ?? threshold);
    const score = scores.get(Number(d["frame_index"]));
    if (score === undefined) continue;
    checked += 1;
    if (score >= threshold) {
      expect(String(d["action"])).toEqual("request_pause_approval");
    } else {
      expect(String(d["action"])).not.toEqual("request_pause_approval");
    }
  }
  expect(checked).toBeGreaterThan(10);

  // Rationale exists only AFTER the first decide — never before the gate.
  const seqOf = (id: string) =>
    events.filter((e) => e.step_id === id).map((e) => e.sequence ?? 0);
  const firstDecide = Math.min(...seqOf("decide"));
  const rationales = seqOf("rationale");
  expect(rationales.length).toBeGreaterThan(0);
  expect(Math.min(...rationales)).toBeGreaterThan(firstDecide);

  // The chip tells the truth about the source.
  const firstAlert = events
    .filter((e) => e.step_id === "decide" && e.status === "done")
    .map((e) => e.payload?.["decision"] as Record<string, unknown>)
    .find((d) => d["action"] !== "continue");
  const source = String(firstAlert?.["rationale_source"] ?? "fallback");
  await expect(page.getByText(`rationale: ${source === "bedrock" ? "bedrock" : "measured fallback"}`).first()).toBeVisible();
});
