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

  // The sustain rule (app/agent/policy.py: a pause needs SUSTAIN_FRAMES=3
  // consecutive sampled frames with score >= pause threshold and confidence
  // >= floor): every pause row is the third such frame, no pause row scores
  // below its threshold, and at least one pause exists — the vision number,
  // not a chatbot, changed what the system did.
  const CONF_FLOOR = 0.55;
  const rows = events
    .filter((e) => e.step_id === "decide" && e.status === "done")
    .map((e) => e.payload?.["decision"] as Record<string, unknown>)
    .filter((d) => d["degraded"] !== true)
    .map((d) => ({
      frame: Number(d["frame_index"]),
      score: Number(d["spaghetti_score"]),
      conf: Number(d["confidence"]),
      action: String(d["action"]),
      thr: Number(d["threshold"]),
    }))
    .sort((a, b) => a.frame - b.frame);
  expect(rows.length).toBeGreaterThan(10);
  const pauses = rows.filter((r) => r.action === "request_pause_approval");
  expect(pauses.length).toBeGreaterThan(0);
  for (const p of pauses) {
    expect(p.score).toBeGreaterThanOrEqual(p.thr);
    expect(p.conf).toBeGreaterThanOrEqual(CONF_FLOOR);
    const i = rows.indexOf(p);
    expect(i).toBeGreaterThanOrEqual(2);
    for (const q of [rows[i - 2]!, rows[i - 1]!]) {
      expect(q.score).toBeGreaterThanOrEqual(p.thr);
      expect(q.conf).toBeGreaterThanOrEqual(CONF_FLOOR);
    }
  }
  for (const r of rows) {
    if (r.score < r.thr) {
      expect(r.action).not.toEqual("request_pause_approval");
    }
  }

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
