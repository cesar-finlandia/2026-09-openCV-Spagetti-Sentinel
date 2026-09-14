// Shared run helpers for scenarios: start runs through the real UI, drain
// approvals over HTTP (fast), and wait for completion via backend truth.
// The FIRST approval of uc02/uc03 is always clicked in the UI; draining the
// remainder over HTTP is test plumbing, not a weakened assertion.
import type { Page } from "@playwright/test";
import {
  collectEvents,
  waitForStep,
  type Envelope,
} from "./envelopes";

export async function startClipRun(
  page: Page,
  clip: string,
  backend = "baseline",
): Promise<string> {
  await page.getByLabel("Demo clip", { exact: true }).selectOption(clip);
  await page.getByLabel("OpenCV backend", { exact: true }).selectOption(backend);
  const [runRes] = await Promise.all([
    page.waitForResponse(
      (r) => r.url().includes("/api/runs") && r.request().method() === "POST",
    ),
    page.getByRole("button", { name: "Start watching" }).click(),
  ]);
  const body = (await runRes.json()) as { run_id: string };
  if (!body.run_id) throw new Error("POST /api/runs returned no run_id");
  return body.run_id;
}

export async function waitSummary(
  page: Page,
  serverURL: string,
  traceId: string,
  timeoutMs = 100_000,
): Promise<Envelope[]> {
  return waitForStep(page, serverURL, traceId, "run-summary", timeoutMs);
}

/** Answer every pending approval over HTTP until run-summary arrives. */
export async function drainApprovals(
  serverURL: string,
  runId: string,
  traceId: string,
  approved = true,
  timeoutMs = 100_000,
): Promise<Envelope[]> {
  const start = Date.now();
  const resolved = new Set<string>();
  while (Date.now() - start < timeoutMs) {
    const events = await collectEvents(serverURL, traceId);
    if (events.some((e) => e.step_id === "run-summary")) return events;
    const done = new Set(
      events
        .filter((e) => e.step_id === "approval-resolved")
        .map((e) => String((e.payload as Record<string, unknown>)?.["approval_id"] ?? "")),
    );
    for (const e of events) {
      if (e.step_id !== "await-approval") continue;
      const aid = String((e.payload as Record<string, unknown>)?.["approval_id"] ?? "");
      if (!aid || done.has(aid) || resolved.has(aid)) continue;
      try {
        await fetch(`${serverURL}/api/runs/${runId}/approve`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ approval_id: aid, approved }),
        });
        resolved.add(aid);
      } catch {
        /* retry on next poll */
      }
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error("timed out draining approvals waiting for run-summary");
}

/**
 * Wait for run-summary, answering any pause prompt in the UI with
 * "Keep printing". Used by no-pause scenarios so a single unexpected prompt
 * surfaces as an assertion failure later, not a 120 s stall.
 */
export async function waitSummaryAnswering(
  page: Page,
  serverURL: string,
  traceId: string,
  timeoutMs = 110_000,
): Promise<Envelope[]> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const dialog = page.getByRole("alertdialog");
    if ((await dialog.count()) > 0) {
      await page
        .getByRole("button", { name: "Keep printing" })
        .click({ timeout: 5_000 })
        .catch(() => {});
    }
    const events = await collectEvents(serverURL, traceId);
    if (events.some((e) => e.step_id === "run-summary")) return events;
    await page.waitForTimeout(1000);
  }
  throw new Error("timed out waiting for run-summary");
}
