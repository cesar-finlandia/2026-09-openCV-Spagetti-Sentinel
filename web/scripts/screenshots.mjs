// DP-UI WU-UI-06 (--audit) and WU-UI-07 (capture) browser gates.
// Uses the repo-root @playwright/test; assumes the API serves the built UI at
// http://localhost:8000/ (start it first: S3_BUCKET= uvicorn app.api.main:app).
import { mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const SHOT_DIR = join(ROOT, "design_documents", "ui-screenshots");
const BASE = "http://localhost:8000/";
const AUDIT = process.argv.includes("--audit");

function fail(msg) {
  console.error(`ASSERT FAIL: ${msg}`);
  process.exit(1);
}

async function apiUp() {
  try {
    const r = await fetch(`${BASE}healthz`);
    if (!r.ok) throw new Error(`status ${r.status}`);
  } catch (e) {
    fail(`API not reachable at ${BASE} (${e.message}). Start it first.`);
  }
}

async function newPage(browser, { width, height, theme, reducedMotion = false }) {
  const context = await browser.newContext({
    viewport: { width, height },
    colorScheme: theme === "dark" ? "dark" : "light",
    reducedMotion: reducedMotion ? "reduce" : "no-preference",
  });
  if (theme) {
    await context.addInitScript(
      (t) => {
        if (!localStorage.getItem("ss-theme")) localStorage.setItem("ss-theme", t);
      },
      theme,
    );
  }
  const page = await context.newPage();
  await page.goto(BASE, { waitUntil: "networkidle" });
  return { context, page };
}

async function startRun(page, fixtureId) {
  await page.getByLabel("Demo clip").selectOption(fixtureId);
  // The server runs one run at a time (409 while busy): retry until the
  // previous run has drained.
  for (let attempt = 0; attempt < 20; attempt++) {
    await page.getByRole("button", { name: "Start watching" }).click();
    const outcome = await page
      .waitForFunction(
        () =>
          document.querySelector(".work-indicator")
            ? "started"
            : document.querySelector(".error-line")?.textContent ?? null,
        undefined,
        { timeout: 20000 },
      )
      .then((h) => h.evaluate((el) => (typeof el === "string" ? el : "started")))
      .catch(() => "timeout");
    if (outcome === "started") return;
    if (typeof outcome === "string" && outcome.includes("already active")) {
      await page.waitForTimeout(20000);
      continue;
    }
    fail(`run did not start: ${outcome}`);
  }
  fail("server still busy after retries (a run never drained)");
}

async function waitScores(page) {
  await page.waitForFunction(
    () => [...document.querySelectorAll(".score-tiles .readout-lg")].some((el) => el.textContent.trim() !== "—"),
    undefined,
    { timeout: 120000 },
  );
}

async function waitApproval(page) {
  await page.getByRole("alertdialog").waitFor({ timeout: 180000 });
}

async function approve(page) {
  await page.getByRole("button", { name: "Approve pause" }).click();
}

async function waitComplete(page) {
  await page.waitForFunction(() => !document.querySelector(".work-indicator"), undefined, { timeout: 600000 });
  await page.waitForSelector(".ss-trace tbody tr", { timeout: 60000 });
}

/** Active run id without side effects: GET /events serves the latest publisher. */
async function learnRunId(page) {
  const tid = await page.evaluate(async () => {
    const r = await fetch("/events");
    const j = await r.json();
    return j.trace_id ?? null;
  });
  if (!tid) fail("could not learn the active run id");
  return tid;
}

/**
 * The alert-dense second half of the spaghetti clip requests approval on
 * nearly every sample; unanswered approvals each cost the agent's 120 s
 * timeout, stretching a run past an hour. The operator (this script) answers
 * every prompt immediately, exactly as in the recorded demo.
 */
async function autoApprover(page, runId) {
  const approved = new Set();
  for (;;) {
    const st = await page
      .evaluate(async (tid) => {
        const r = await fetch(`/api/runs/${tid}`);
        return r.ok ? r.json() : { status: "unknown" };
      }, runId)
      .catch(() => ({ status: "unknown" }));
    if (st.status === "done" || st.status === "error") return st.status;
    const pendings = await page
      .evaluate(async (tid) => {
        const r = await fetch(`/events?trace_id=${tid}`);
        const j = await r.json();
        const resolved = new Set(
          j.events.filter((e) => e.step_id === "approval-resolved").map((e) => e.payload.approval_id),
        );
        return j.events
          .filter((e) => e.step_id === "await-approval" && !resolved.has(e.payload.approval_id))
          .map((e) => e.payload.approval_id);
      }, runId)
      .catch(() => []);
    for (const aid of pendings) {
      if (approved.has(aid)) continue;
      await page
        .evaluate(async ({ tid, aid: id }) => {
          await fetch(`/api/runs/${tid}/approve`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ approval_id: id, approved: true }),
          });
        }, { tid: runId, aid })
        .catch(() => {});
      approved.add(aid);
    }
    await page.waitForTimeout(3000);
  }
}

async function waitServerDone(page, runId) {
  await page.waitForFunction(
    async (tid) => {
      try {
        const r = await fetch(`/api/runs/${tid}`);
        if (!r.ok) return false;
        const j = await r.json();
        return j.status === "done" || j.status === "error";
      } catch {
        return false;
      }
    },
    runId,
    { timeout: 600000 },
  );
}

async function audit() {
  const browser = await chromium.launch();

  // Desktop 1240x900 checks 1-4 on a live run.
  {
    const { context, page } = await newPage(browser, { width: 1240, height: 900, theme: "light" });
    await startRun(page, "good-first-layer");
    await waitScores(page);
    await page.waitForSelector(".ss-trace tbody tr", { timeout: 120000 });

    const sw = await page.evaluate(() => document.documentElement.scrollWidth);
    if (sw > 1240) fail(`horizontal scroll at 1240px (scrollWidth ${sw})`);

    const smallTd = await page.evaluate(() =>
      [...document.querySelectorAll(".ss-trace td")].filter(
        (td) => parseFloat(getComputedStyle(td).fontSize) < 14,
      ).length,
    );
    if (smallTd > 0) fail(`${smallTd} trace cells below 14px`);

    for (let i = 0; i < 80; i++) {
      await page.keyboard.press("Tab");
      const bad = await page.evaluate(() => {
        const el = document.activeElement;
        if (!el || el === document.body) return null;
        const tag = el.tagName.toLowerCase();
        if (!["button", "a", "input", "select", "summary", "video"].includes(tag)) return null;
        return getComputedStyle(el).outlineStyle === "none" ? tag : null;
      });
      if (bad) fail(`focus invisible on <${bad}>`);
    }

    const unnamed = await page.evaluate(() =>
      [...document.querySelectorAll("button, a, input, select")].filter((el) => {
        if (el.tagName.toLowerCase() === "input" && el.type === "hidden") return false;
        const name =
          el.getAttribute("aria-label") ||
          (el.textContent || "").trim() ||
          (el.labels && [...el.labels].map((l) => l.textContent).join(" ").trim()) ||
          el.getAttribute("alt") ||
          "";
        return !name;
      }).length,
    );
    if (unnamed > 0) fail(`${unnamed} controls without an accessible name`);

    // Leave the server clean for the next stage.
    await waitApproval(page).catch(() => {});
    const alert = await page.getByRole("alertdialog").count();
    if (alert > 0) await approve(page);
    await waitComplete(page).catch(() => {});
    await context.close();
  }

  // Mobile 390x844 check 5 on a second live run.
  {
    const { context, page } = await newPage(browser, { width: 390, height: 844, theme: "light" });
    await startRun(page, "good-first-layer");
    await waitScores(page);
    const sw = await page.evaluate(() => document.documentElement.scrollWidth);
    if (sw > 390) fail(`horizontal scroll at 390px (scrollWidth ${sw})`);
    const oneRow = await page.evaluate(() => {
      const tiles = [...document.querySelectorAll(".score-tiles > *")];
      if (tiles.length < 2) return false;
      const a = tiles[0].getBoundingClientRect();
      const b = tiles[1].getBoundingClientRect();
      return Math.abs(a.top - b.top) < 4;
    });
    if (!oneRow) fail("ScoreTiles not on one row at 390px");
    await waitComplete(page);

    // Check 6: theme flips and persists across a reload.
    const before = await page.evaluate(() => document.documentElement.dataset.theme);
    await page.getByRole("switch").click();
    const after = await page.evaluate(() => document.documentElement.dataset.theme);
    if (before === after) fail("theme toggle did not flip data-theme");
    await page.reload({ waitUntil: "networkidle" });
    const persisted = await page.evaluate(() => document.documentElement.dataset.theme);
    if (persisted !== after) fail(`theme did not persist across reload (${persisted} !== ${after})`);
    await context.close();
  }

  // Reduced-motion check 7 on a third run.
  {
    const { context, page } = await newPage(browser, {
      width: 1240, height: 900, theme: "light", reducedMotion: true,
    });
    await startRun(page, "good-first-layer");
    await page.waitForSelector(".work-indicator__bar", { timeout: 120000 });
    const durMs = await page.evaluate(() => {
      const raw = getComputedStyle(document.querySelector(".work-indicator__bar")).animationDuration;
      const m = raw.trim().match(/^([\d.eE+-]+)(m?s)$/);
      if (!m) return NaN;
      return m[2] === "ms" ? parseFloat(m[1]) : parseFloat(m[1]) * 1000;
    });
    // 0.01ms — Chromium may serialise it as "1e-05s", so compare numerically.
    if (!(Math.abs(durMs - 0.01) < 1e-9)) fail(`reduced motion not applied (duration ${durMs}ms)`);
    await waitApproval(page).catch(() => {});
    const alert = await page.getByRole("alertdialog").count();
    if (alert > 0) await approve(page);
    await waitComplete(page).catch(() => {});
    await context.close();
  }

  await browser.close();
  console.log("a11y-ok");
}

async function capture() {
  const browser = await chromium.launch();
  mkdirSync(SHOT_DIR, { recursive: true });
  const shot = (page, name) => page.screenshot({ path: join(SHOT_DIR, name) });

  async function fullRun(theme, names) {
    const { context, page } = await newPage(browser, { width: 1440, height: 900, theme });
    await shot(page, names.empty);
    await startRun(page, "spaghetti");
    await page.waitForSelector(".work-indicator", { timeout: 120000 });
    const runId = await learnRunId(page);
    const line = await page.evaluate(
      () => document.querySelector(".work-indicator .small")?.textContent?.trim() ?? "",
    );
    if (!line) fail("WorkIndicator text line empty at capture time");
    await waitScores(page);
    await shot(page, names.running);
    // Degraded capture rides on the light run: local evidence fallback marks
    // envelopes degraded, so the banner is up while the run is live.
    if (names.degraded) {
      await page.waitForSelector(".degraded-banner", { timeout: 180000 }).catch(() => {});
      await shot(page, names.degraded);
    }
    await waitApproval(page);
    await shot(page, names.approval);
    await approve(page);
    await Promise.all([autoApprover(page, runId), waitServerDone(page, runId)]);
    await waitComplete(page);
    await shot(page, names.complete);
    await page.setViewportSize({ width: 1920, height: 1080 });
    await page.waitForFunction(
      () => document.querySelectorAll(".ss-trace tbody tr").length >= 20,
      undefined,
      { timeout: 60000 },
    );
    const alertRow = await page.evaluate(
      () => [...document.querySelectorAll(".ss-trace tbody tr")].some((tr) => tr.className.includes("row-alert")),
    );
    if (!alertRow) fail("no alert row in the trace at capture time");
    await page.evaluate(() => document.querySelector(".ss-trace")?.scrollIntoView({ block: "start" }));
    await page.waitForTimeout(400);
    await shot(page, names.trace);
    await context.close();
  }

  await fullRun("light", {
    empty: "01-empty-light.png", running: "03-running-light.png",
    approval: "05-approval-light.png", complete: "07-complete-light.png",
    trace: "09-trace-light.png", degraded: "11-degraded-light.png",
  });
  await fullRun("dark", {
    empty: "02-empty-dark.png", running: "04-running-dark.png",
    approval: "06-approval-dark.png", complete: "08-complete-dark.png",
    trace: "10-trace-dark.png",
  });

  // Error state: the API answers 400, the RunControls error path renders.
  {
    const { context, page } = await newPage(browser, { width: 1440, height: 900, theme: "light" });
    await page.route("**/api/runs", (route) =>
      route.fulfill({
        status: 400,
        contentType: "application/json",
        body: JSON.stringify({ detail: "cannot open source: FileNotFoundError" }),
      }),
    );
    await page.getByRole("button", { name: "Start watching" }).click();
    await page.waitForSelector(".control--error", { timeout: 30000 });
    await shot(page, "12-error-light.png");
    await context.close();
  }

  for (const theme of ["light", "dark"]) {
    const { context, page } = await newPage(browser, { width: 390, height: 844, theme });
    await shot(page, theme === "light" ? "13-mobile-light.png" : "14-mobile-dark.png");
    await context.close();
  }

  await browser.close();
  console.log("screenshots: 14 files");
}

await apiUp();
if (AUDIT) {
  await audit();
} else {
  await capture();
}
