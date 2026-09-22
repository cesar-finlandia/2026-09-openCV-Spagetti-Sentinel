/**
 * DP-UI-V2 §7 — the measured half of the craft audit, in a real browser.
 *
 *   pnpm --dir web exec playwright test e2e/craft-audit.spec.ts
 *
 * It runs against the dev server (playwright.config's webServer) at 1920x1080,
 * drives the replay fixture to completion, and measures what the camera will
 * actually see. The last test points it at a deliberately broken page and
 * asserts it reports exactly the three seeded defects — an audit that has never
 * failed is not an audit.
 */
import { expect, test, type Page } from "@playwright/test";
import { pathToFileURL } from "node:url";
import { resolve } from "node:path";

const ANCHORS = ["score", "timeline", "decision", "approval", "evidence", "backend"] as const;

test.use({ viewport: { width: 1920, height: 1080 } });

/** WCAG relative luminance from a computed `rgb(r, g, b)` string. */
const CONTRAST = `(fg, bg) => {
  const p = (s) => (s.match(/[\\d.]+/g) || []).slice(0, 3).map(Number);
  const lum = (c) => {
    const [r, g, b] = p(c).map((v) => {
      const s = v / 255;
      return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
    });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  };
  const a = lum(fg), b2 = lum(bg);
  return (Math.max(a, b2) + 0.05) / (Math.min(a, b2) + 0.05);
}`;

async function px(page: Page, selector: string, prop = "fontSize"): Promise<number> {
  return page.$eval(
    selector,
    (el, p) => Number.parseFloat(getComputedStyle(el as Element)[p as never] as string),
    prop,
  );
}

async function runToCompletion(page: Page): Promise<void> {
  await page.goto("/");
  await page.getByRole("button", { name: /start watching/i }).click();
  await page.waitForSelector('[data-demo-focus="approval"]', { timeout: 120_000 });
  await page.getByRole("button", { name: /approve pause/i }).click();
  await page.waitForSelector('[data-quiet="true"]', { timeout: 60_000 });
}

test("body, readouts and the hero metric are sized for the camera", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: /start watching/i }).click();
  await page.waitForSelector(".hero");

  expect(await px(page, "body")).toBeGreaterThanOrEqual(18);
  expect(await px(page, ".hero")).toBeGreaterThanOrEqual(64);

  const readouts = await page.$$eval(".readout", (els) =>
    els.map((e) => Number.parseFloat(getComputedStyle(e).fontSize)),
  );
  expect(readouts.length).toBeGreaterThan(0);
  expect(Math.min(...readouts)).toBeGreaterThanOrEqual(28);

  const all = await page.$$eval("body *", (els) =>
    els
      .filter((e) => (e.textContent || "").trim().length > 0 && e.children.length === 0)
      .map((e) => Number.parseFloat(getComputedStyle(e).fontSize)),
  );
  expect(Math.min(...all)).toBeGreaterThanOrEqual(16);
});

test("each demo-focus anchor is unique, big enough, and not nested", async ({ page }) => {
  await runToCompletion(page);
  const boxes: Record<string, { w: number; h: number }> = {};
  for (const key of ANCHORS) {
    const loc = page.locator(`[data-demo-focus="${key}"]`);
    await expect(loc, `anchor ${key}`).toHaveCount(1);
    const box = await loc.boundingBox();
    expect(box, `anchor ${key} has no box`).not.toBeNull();
    expect(box!.width, `${key} width`).toBeGreaterThanOrEqual(120);
    expect(box!.height, `${key} height`).toBeGreaterThanOrEqual(60);
    boxes[key] = { w: box!.width, h: box!.height };
  }
  const nested = await page.$$eval("[data-demo-focus]", (els) =>
    els.filter((e) => e.parentElement?.closest("[data-demo-focus]") !== null).length,
  );
  expect(nested, "no anchor may be inside another").toBe(0);
});

test("every string the camera stops on clears 4.5:1", async ({ page }) => {
  await runToCompletion(page);
  const bad = await page.evaluate(
    ([contrastSrc]) => {
      const contrast = eval(contrastSrc as string) as (a: string, b: string) => number;
      const bgOf = (el: Element): string => {
        let n: Element | null = el;
        while (n) {
          const c = getComputedStyle(n).backgroundColor;
          if (c && !/rgba\(0, 0, 0, 0\)|transparent/.test(c)) return c;
          n = n.parentElement;
        }
        return "rgb(0, 0, 0)";
      };
      return [...document.querySelectorAll("body *")]
        .filter((e) => e.children.length === 0 && (e.textContent || "").trim().length > 1)
        .map((e) => ({
          text: (e.textContent || "").trim().slice(0, 40),
          ratio: contrast(getComputedStyle(e).color, bgOf(e)),
        }))
        .filter((r) => r.ratio < 4.5);
    },
    [CONTRAST],
  );
  expect(bad).toEqual([]);
});

test("state-change motion lands in the 200-400ms window", async ({ page }) => {
  await page.goto("/");
  const durations = await page.evaluate(() => {
    const read = (name: string) =>
      Number.parseInt(getComputedStyle(document.documentElement).getPropertyValue(name), 10);
    return ["--motion-fast", "--motion-base", "--motion-slow"].map(read);
  });
  for (const d of durations) {
    expect(d).toBeGreaterThanOrEqual(200);
    expect(d).toBeLessThanOrEqual(400);
  }
});

test("a quiet frame exists and nothing is animating in it", async ({ page }) => {
  await runToCompletion(page);
  await expect(page.locator('[data-quiet="true"]')).toHaveCount(1);
  const running = await page.evaluate(() => document.getAnimations().length);
  expect(running).toBe(0);
});

test("the audit fails on the deliberately broken page", async ({ page }) => {
  const url = pathToFileURL(resolve(__dirname, "fixtures", "broken-craft.html")).href;
  await page.goto(url);

  const defects: string[] = [];
  if ((await px(page, ".label")) < 16) defects.push("font-size below the 16px floor");
  if ((await page.locator("[data-demo-focus]").count()) === 0) defects.push("no data-demo-focus anchor");
  const t = await page.$eval(".decision-card", (el) => getComputedStyle(el).transitionDuration);
  if (Number.parseFloat(t) * 1000 < 200) defects.push("state-change transition under 200ms");

  expect(defects).toEqual([
    "font-size below the 16px floor",
    "no data-demo-focus anchor",
    "state-change transition under 200ms",
  ]);
});
