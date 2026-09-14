// uc08 — Maya uses her own footage.
// NOTE (fix-log #5): /api/runs/upload stores bytes as uploads/<uuid>.<ext>;
// the run-start source names that stored copy, not the original filename.
import * as path from "node:path";
import { appTest, expect } from "../fixtures/app";
import { collectEvents } from "../fixtures/envelopes";
import { drainApprovals } from "../fixtures/runs";

appTest("uc08 an uploaded clip starts a run that reaches summary", async ({
  page,
  serverURL,
}) => {
  await page.goto(`${serverURL}/`);
  const clipPath = path.join(process.cwd(), "fixtures", "clips", "spaghetti.mp4");
  const [upRes] = await Promise.all([
    page.waitForResponse(
      (r) => r.url().includes("/api/runs/upload") && r.request().method() === "POST",
    ),
    page.getByLabel("Upload your own clip").setInputFiles(clipPath),
  ]);
  expect(upRes.ok()).toBe(true);
  const started = (await upRes.json()) as { run_id: string };
  expect(started.run_id ?? "").not.toEqual("");

  const events = await collectEvents(serverURL, started.run_id);
  const runStart = events.find((e) => e.step_id === "run-start");
  const source = String((runStart?.payload as Record<string, unknown> | undefined)?.["source"] ?? "");
  expect(source).toMatch(/uploads/);
  expect(source.endsWith(".mp4")).toBe(true);

  const done = await drainApprovals(serverURL, started.run_id, started.run_id, true);
  expect(done.some((e) => e.step_id === "run-summary")).toBe(true);
});
