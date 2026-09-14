# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: scenarios\uc06-backend-cool-vs-baseline.spec.ts >> uc06 backend switch is reported and both backends do real work
- Location: e2e\scenarios\uc06-backend-cool-vs-baseline.spec.ts:27:1

# Error details

```
Error: expect(locator).toHaveAttribute(expected) failed

Locator: getByLabel(/backend|COOL backend/)
Expected: "baseline OpenCV backend"
Error: strict mode violation: getByLabel(/backend|COOL backend/) resolved to 2 elements:
    1) <span class="pill" aria-label="baseline OpenCV backend">…</span> aka getByLabel('baseline OpenCV backend')
    2) <select id="run-backend">…</select> aka getByLabel('OpenCV backend', { exact: true })

Call log:
  - Expect "toHaveAttribute" with timeout 5000ms
  - waiting for getByLabel(/backend|COOL backend/)

```

# Page snapshot

```yaml
- generic [ref=e3]:
  - banner [ref=e4]:
    - generic [ref=e5]: Spaghetti Sentinel
    - generic [ref=e10]:
      - generic "baseline OpenCV backend" [ref=e11]:
        - generic [ref=e13]: baseline OpenCV 5.0.0
        - generic [ref=e14]: e2e-2026-09-13T20-32-08-548Z
      - 'status "stream status: connecting" [ref=e15]': connecting
      - switch "Switch to dark theme" [ref=e17] [cursor=pointer]
  - status "Starting the run — connecting to the live stream" [ref=e22]:
    - generic [ref=e25]:
      - generic [ref=e26]: Starting the run — connecting to the live stream
      - generic [ref=e27]: 0.2s
  - generic [ref=e28]:
    - generic [ref=e29]:
      - status "scores not yet available" [ref=e31]:
        - generic [ref=e32]:
          - text: Spaghetti score
          - generic [ref=e33]: —
          - generic [ref=e34]: waiting for the first frame
        - generic [ref=e35]:
          - text: Confidence
          - generic [ref=e36]: —
          - generic [ref=e37]: waiting for the first frame
      - region "Confidence timeline" [ref=e39]:
        - generic [ref=e41]:
          - generic [ref=e42]: spaghetti score
          - generic [ref=e44]: confidence
          - generic [ref=e46]: pause threshold
        - status [ref=e48]: Waiting for the first measurements…
      - region "Latest decision" [ref=e50]:
        - status [ref=e52]: No decision yet — the agent reports here once the first frames are analysed.
      - region "Evidence" [ref=e54]:
        - status [ref=e56]: No evidence clips yet — stills and clips saved during the run appear here.
    - generic [ref=e57]:
      - region "Start a run" [ref=e59]:
        - generic [ref=e61]:
          - generic [ref=e62]: Demo clip
          - combobox "Demo clip" [disabled] [ref=e63]:
            - option "first available clip" [selected]
            - option "good-first-layer — nominal"
            - option "stringing — warning"
            - option "spaghetti — failure"
            - option "lighting-shift — nominal"
        - generic [ref=e64]:
          - generic [ref=e65]: OpenCV backend
          - combobox "OpenCV backend" [disabled] [ref=e66]:
            - option "baseline" [selected]
            - option "cool"
        - generic [ref=e68]:
          - checkbox "Replay (offline) Runs from cached frames — no AWS, no network." [checked] [disabled] [ref=e69]
          - generic [ref=e70]: Replay (offline)Runs from cached frames — no AWS, no network.
        - generic [ref=e71]:
          - button "Start watching" [disabled] [ref=e72]
          - button "Upload your own clip" [disabled] [ref=e73]
      - region "Pipeline progress" [ref=e75]:
        - generic [ref=e76]: Pipeline
        - generic [ref=e77]: Awaiting progress…
  - region "Decision trace" [ref=e80]:
    - group [ref=e82]:
      - generic "Agent tools (4)" [ref=e83]
    - status [ref=e84]: The trace fills in as frames are scored and decisions are made.
  - contentinfo "About this system" [ref=e85]:
    - paragraph [ref=e86]: This system recommends; it never controls the printer.
    - paragraph [ref=e87]: build e2e-2026-09-13T20-32-08-548Z
```

# Test source

```ts
  1  | // uc06 — mandatory technology: OpenCV 5 / COOL, reported at runtime.
  2  | // NOTE (fix-log #3): with cool_version null on this host both runs honestly
  3  | // render the baseline badge; the COOL branch is re-exercised after the COOL
  4  | // redeploy. What this scenario proves now: per-run backend identity, a real
  5  | // OpenCV 5 version on the wire, and real per-operation timings.
  6  | import type { Page } from "@playwright/test";
  7  | import { appTest, expect } from "../fixtures/app";
  8  | import { collectEvents } from "../fixtures/envelopes";
  9  | import { startClipRun, waitSummaryAnswering } from "../fixtures/runs";
  10 | 
  11 | const OPS = [
  12 |   "resize",
  13 |   "cvt_gray",
  14 |   "gaussian_blur",
  15 |   "threshold",
  16 |   "morphology",
  17 |   "sobel",
  18 | ];
  19 | 
  20 | async function runOnce(page: Page, serverURL: string, backend: string) {
  21 |   await page.goto(`${serverURL}/`);
  22 |   const traceId = await startClipRun(page, "good-first-layer", backend);
  23 |   const events = await waitSummaryAnswering(page, serverURL, traceId);
  24 |   return { traceId, events };
  25 | }
  26 | 
  27 | appTest("uc06 backend switch is reported and both backends do real work", async ({
  28 |   page,
  29 |   serverURL,
  30 | }) => {
  31 |   const health = (await (await fetch(`${serverURL}/healthz`)).json()) as {
  32 |     cool_version: string | null;
  33 |     opencv_version: string;
  34 |     arch: string;
  35 |   };
  36 | 
  37 |   const seen: Record<string, { opencv: string; backend: string; ops: string[] }> = {};
  38 |   for (const backend of ["cool", "baseline"]) {
  39 |     const { events } = await runOnce(page, serverURL, backend);
  40 |     const start = events.find((e) => e.step_id === "run-start");
  41 |     const p = (start?.payload ?? {}) as Record<string, unknown>;
  42 |     expect(String(p["opencv_version"] ?? "")).toMatch(/^5\./);
  43 |     // R1 fallback is honest: requesting "cool" without a COOL build reports
  44 |     // the baseline backend (with coolVersion null); with COOL installed it
  45 |     // reports "cool".
  46 |     if (backend === "cool" && health.cool_version === null) {
  47 |       expect(String(p["backend"] ?? "")).toEqual("baseline");
  48 |     } else {
  49 |       expect(String(p["backend"] ?? "")).toEqual(backend);
  50 |     }
  51 |     const perceives = events.filter(
  52 |       (e) => e.step_id === "perceive" && e.status === "done",
  53 |     );
  54 |     expect(perceives.length).toBeGreaterThan(10);
  55 |     const ops = Object.keys(
  56 |       ((perceives[0]?.payload?.["scores"] as Record<string, unknown>)?.[
  57 |         "ops_ms"
  58 |       ] as Record<string, unknown>) ?? {},
  59 |     );
  60 |     for (const op of OPS) expect(ops).toContain(op);
  61 | 
  62 |     // The badge is honest about what is installed on this host.
  63 |     const badge = page.getByLabel(/backend|COOL backend/);
  64 |     if (health.cool_version !== null) {
  65 |       await expect(badge).toHaveAttribute("aria-label", `COOL backend on ${health.arch}`);
  66 |     } else {
> 67 |       await expect(badge).toHaveAttribute("aria-label", "baseline OpenCV backend");
     |                           ^ Error: expect(locator).toHaveAttribute(expected) failed
  68 |     }
  69 |     seen[backend] = { opencv: String(p["opencv_version"]), backend: String(p["backend"]), ops };
  70 |   }
  71 |   expect(seen["cool"]!.opencv).toMatch(/^5\./);
  72 |   expect(seen["baseline"]!.opencv).toMatch(/^5\./);
  73 |   void collectEvents;
  74 | });
  75 | 
```