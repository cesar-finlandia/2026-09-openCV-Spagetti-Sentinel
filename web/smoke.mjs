// DP-UI WU-05 browser smoke: drives the real stack end to end.
// 1. Open http://localhost:8000/. 2. Start spaghetti/sample_every_n=6.
// 3. Answer every approval prompt (the failure clip asks more than once).
// 4. Wait for Finished + trace rows, screenshot, print ui-smoke-ok <rowCount>.
import { mkdirSync } from "node:fs";
import { chromium } from "@playwright/test";

const BASE = process.env.SMOKE_URL || "http://localhost:8000";

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
try {
  await page.goto(`${BASE}/`, { waitUntil: "networkidle", timeout: 30000 });
  await page.locator("select").first().waitFor({ timeout: 15000 });
  await page.locator("select").first().selectOption("spaghetti");
  await page.getByRole("button", { name: "Start" }).click();
  mkdirSync("web/.smoke", { recursive: true });
  // Answer approvals until the run finishes (up to ~6 minutes: an unanswered
  // prompt waits out the 120 s approval timeout).
  let shot = false;
  const deadline = Date.now() + 360000;
  let finished = false;
  while (Date.now() < deadline) {
    if (await page.getByText("Finished", { exact: false }).count()) {
      finished = true;
      break;
    }
    const dialog = page.getByRole("alertdialog");
    if (await dialog.count()) {
      if (!shot) {
        await page.screenshot({ path: "web/.smoke/approval.png" });
        shot = true;
      }
      await page.getByRole("button", { name: "Approve pause" }).click();
    }
    await page.waitForTimeout(2000);
  }
  if (!finished) throw new Error("run did not finish in time");
  await page.waitForFunction(
    () => document.querySelectorAll("table.ss-trace tbody tr").length >= 20,
    { timeout: 60000 },
  );
  const rows = await page.locator("table.ss-trace tbody tr").count();
  await page.screenshot({ path: "web/.smoke/trace.png" });
  console.log(`ui-smoke-ok ${rows}`);
} finally {
  await browser.close();
}
