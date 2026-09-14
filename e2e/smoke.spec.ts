// Smoke suite — the cross-plan interface (DP-E2E §5.5). The thinnest path
// proving the product is alive and doing real work. Target comes from
// BASE_URL (deployed gates) with a localhost default. Never writes to the
// repository; safe to run repeatedly against production.
import { appTest, expect } from "./fixtures/app";
import { collectEvents } from "./fixtures/envelopes";

// eslint-disable-next-line no-console
const log = console.log;

appTest("smoke: deployed product runs spaghetti to an approved pause", async ({
  page,
  serverURL,
}) => {
  // 1. Health.
  const healthRes = await fetch(`${serverURL}/healthz`);
  expect(healthRes.ok).toBe(true);
  const health = (await healthRes.json()) as {
    status?: string;
    build_marker?: string;
  };
  expect(["ok", "degraded"]).toContain(health.status);
  const marker = health.build_marker ?? "";
  expect(marker).not.toEqual("");
  log(`smoke: health ${health.status} marker=${marker}`);

  // 2. Wordmark + Start button.
  await page.goto(`${serverURL}/`);
  await expect(page.getByText("Spaghetti Sentinel").first()).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Start watching" }),
  ).toBeVisible();

  // 3–4. Start spaghetti; the work indicator proves real work.
  await page.getByLabel("Demo clip", { exact: true }).selectOption("spaghetti");
  const [runRes] = await Promise.all([
    page.waitForResponse(
      (r) => r.url().includes("/api/runs") && r.request().method() === "POST",
    ),
    page.getByRole("button", { name: "Start watching" }).click(),
  ]);
  const started = (await runRes.json()) as { run_id: string };
  await expect(page.getByTestId("work-indicator-text")).not.toBeEmpty({
    timeout: 30_000,
  });

  // 5. Approval dialog quotes a score and a threshold.
  const dialog = page.getByRole("alertdialog");
  await expect(dialog).toBeVisible({ timeout: 90_000 });
  await expect(dialog).toContainText(/scored [\d.]+ against a threshold of [\d.]+/);

  // 6. Approve; the panel unmounts.
  await page.getByRole("button", { name: "Approve pause" }).click();
  await expect(page.getByRole("alertdialog")).toHaveCount(0, { timeout: 15_000 });

  // 7. Trace fills with ≥10 rows and a pause row (answer the rest over HTTP).
  const traceId = started.run_id;
  const start = Date.now();
  const resolved = new Set<string>();
  let rows = 0;
  while (Date.now() - start < 100_000) {
    const events = await collectEvents(serverURL, traceId);
    if (events.some((e) => e.step_id === "run-summary")) break;
    const done = new Set(
      events
        .filter((e) => e.step_id === "approval-resolved")
        .map((e) => String((e.payload as Record<string, unknown>)?.["approval_id"] ?? "")),
    );
    for (const e of events) {
      if (e.step_id !== "await-approval") continue;
      const aid = String((e.payload as Record<string, unknown>)?.["approval_id"] ?? "");
      if (!aid || done.has(aid) || resolved.has(aid)) continue;
      await fetch(`${serverURL}/api/runs/${traceId}/approve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ approval_id: aid, approved: true }),
      }).catch(() => {});
      resolved.add(aid);
    }
    const table = page.getByRole("table");
    if ((await table.count()) > 0) {
      rows = await table.getByRole("row").count();
      if (rows >= 11) break;
    }
    await page.waitForTimeout(1000);
  }
  expect(rows).toBeGreaterThanOrEqual(11);
  await expect(page.locator("tr.row-alert").first()).toContainText(
    "request_pause_approval",
  );

  // 8. Zero unexpected console errors is enforced by the fixture gate.
  // 9. The gate line downstream plans match on.
  log(`smoke-ok ${serverURL} ${marker} ${rows}`);
});
