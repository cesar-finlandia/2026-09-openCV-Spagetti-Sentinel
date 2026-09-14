// uc13 — every control does something: full inventory against the manifest
// of controls exercised across the suite, plus the theme toggle round-trip.
import { appTest, expect } from "../fixtures/app";
import { startClipRun, waitSummaryAnswering } from "../fixtures/runs";

// Accessible names clicked by uc01–uc12 (strategy.md control table).
const CLICKED_ELSEWHERE = [
  "Start watching",
  "Approve pause",
  "Keep printing",
  "Upload your own clip",
  "Agent tools",
];
const DYNAMIC_PREFIX = /^(open evidence|download evidence|evidence (clip|still))/i;

appTest("uc13 control inventory and theme round-trip", async ({
  page,
  serverURL,
}) => {
  await page.goto(`${serverURL}/`);
  // A run with evidence present so the evidence links exist for inventory
  // (evidence only materialises off replay — fix-log #12).
  await page.getByLabel("Replay (offline)").uncheck();
  const traceId = await startClipRun(page, "stringing", "baseline");
  await waitSummaryAnswering(page, serverURL, traceId);

  const unaccounted: string[] = [];
  for (const el of await page
    .locator("button, a[href], input, select, [role=switch]")
    .all()) {
    if (!(await el.isVisible())) continue;
    const name =
      (await el.getAttribute("aria-label")) ??
      (await el.innerText()).trim().split("\n")[0]?.slice(0, 60) ??
      (await el.getAttribute("value")) ??
      el.toString();
    const label = (name ?? "").trim();
    if (!label) continue;
    if (CLICKED_ELSEWHERE.some((n) => label.includes(n))) continue;
    if (DYNAMIC_PREFIX.test(label)) continue;
    // Selects, checkboxes and the theme switch are exercised below/by suite.
    const tag = await el.evaluate((n) =>
      n instanceof HTMLSelectElement
        ? "select"
        : n instanceof HTMLInputElement
          ? `input:${n.type}`
          : n.getAttribute("role") === "switch"
            ? "switch"
            : n.tagName.toLowerCase(),
    );
    if (tag === "select" || tag.startsWith("input:") || tag === "switch") {
      continue;
    }
    unaccounted.push(`${tag} "${label}"`);
  }
  expect(unaccounted, "controls with no exercising scenario").toEqual([]);

  // The theme toggle flips data-theme and survives a reload.
  const toggle = page.getByRole("switch").first();
  const html = page.locator("html");
  const before = await html.getAttribute("data-theme");
  await toggle.click();
  const after = await html.getAttribute("data-theme");
  expect(after).not.toEqual(before);
  await page.reload();
  expect(await page.locator("html").getAttribute("data-theme")).toEqual(after);
});
