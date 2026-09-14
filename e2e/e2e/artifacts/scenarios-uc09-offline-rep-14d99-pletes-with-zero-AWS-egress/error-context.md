# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: scenarios\uc09-offline-replay.spec.ts >> uc09 offline replay completes with zero AWS egress
- Location: e2e\scenarios\uc09-offline-replay.spec.ts:5:1

# Error details

```
Error: locator.selectOption: Error: strict mode violation: getByLabel('OpenCV backend') resolved to 2 elements:
    1) <span class="pill" aria-label="baseline OpenCV backend">…</span> aka getByLabel('baseline OpenCV backend')
    2) <select id="run-backend">…</select> aka getByLabel('OpenCV backend', { exact: true })

Call log:
  - waiting for getByLabel('OpenCV backend')

```

# Page snapshot

```yaml
- generic [ref=e3]:
  - banner [ref=e4]:
    - generic [ref=e5]: Spaghetti Sentinel
    - generic [ref=e10]:
      - generic "baseline OpenCV backend" [ref=e11]:
        - generic [ref=e13]: baseline OpenCV 5.0.0
        - generic [ref=e14]: e2e-2026-09-13T19-35-50-752Z
      - 'status "stream status: connecting" [ref=e15]': connecting
      - switch "Switch to dark theme" [ref=e17] [cursor=pointer]
  - generic [ref=e22]:
    - heading "Nothing is being watched yet." [level=1] [ref=e23]
    - paragraph [ref=e24]: Pick a demo clip and press “Start watching”. The whole run takes about 30 seconds.
    - region "Start a run" [ref=e25]:
      - generic [ref=e27]:
        - generic [ref=e28]: Demo clip
        - combobox "Demo clip" [ref=e29]:
          - option "first available clip"
          - option "good-first-layer — nominal" [selected]
          - option "stringing — warning"
          - option "spaghetti — failure"
          - option "lighting-shift — nominal"
      - generic [ref=e30]:
        - generic [ref=e31]: OpenCV backend
        - combobox "OpenCV backend" [ref=e32]:
          - option "baseline" [selected]
          - option "cool"
      - generic [ref=e34]:
        - checkbox "Replay (offline) Runs from cached frames — no AWS, no network." [checked] [ref=e35]
        - generic [ref=e36]: Replay (offline)Runs from cached frames — no AWS, no network.
      - generic [ref=e37]:
        - button "Start watching" [ref=e38] [cursor=pointer]
        - button "Upload your own clip" [ref=e39] [cursor=pointer]
  - contentinfo "About this system" [ref=e40]:
    - paragraph [ref=e41]: This system recommends; it never controls the printer.
    - paragraph [ref=e42]: build e2e-2026-09-13T19-35-50-752Z
```

# Test source

```ts
  1   | // Shared run helpers for scenarios: start runs through the real UI, drain
  2   | // approvals over HTTP (fast), and wait for completion via backend truth.
  3   | // The FIRST approval of uc02/uc03 is always clicked in the UI; draining the
  4   | // remainder over HTTP is test plumbing, not a weakened assertion.
  5   | import type { Page } from "@playwright/test";
  6   | import {
  7   |   collectEvents,
  8   |   waitForStep,
  9   |   type Envelope,
  10  | } from "./envelopes";
  11  | 
  12  | export async function startClipRun(
  13  |   page: Page,
  14  |   clip: string,
  15  |   backend = "baseline",
  16  | ): Promise<string> {
  17  |   await page.getByLabel("Demo clip").selectOption(clip);
> 18  |   await page.getByLabel("OpenCV backend").selectOption(backend);
      |                                           ^ Error: locator.selectOption: Error: strict mode violation: getByLabel('OpenCV backend') resolved to 2 elements:
  19  |   const [runRes] = await Promise.all([
  20  |     page.waitForResponse(
  21  |       (r) => r.url().includes("/api/runs") && r.request().method() === "POST",
  22  |     ),
  23  |     page.getByRole("button", { name: "Start watching" }).click(),
  24  |   ]);
  25  |   const body = (await runRes.json()) as { run_id: string };
  26  |   if (!body.run_id) throw new Error("POST /api/runs returned no run_id");
  27  |   return body.run_id;
  28  | }
  29  | 
  30  | export async function waitSummary(
  31  |   page: Page,
  32  |   serverURL: string,
  33  |   traceId: string,
  34  |   timeoutMs = 100_000,
  35  | ): Promise<Envelope[]> {
  36  |   return waitForStep(page, serverURL, traceId, "run-summary", timeoutMs);
  37  | }
  38  | 
  39  | /** Answer every pending approval over HTTP until run-summary arrives. */
  40  | export async function drainApprovals(
  41  |   serverURL: string,
  42  |   runId: string,
  43  |   traceId: string,
  44  |   approved = true,
  45  |   timeoutMs = 100_000,
  46  | ): Promise<Envelope[]> {
  47  |   const start = Date.now();
  48  |   const resolved = new Set<string>();
  49  |   while (Date.now() - start < timeoutMs) {
  50  |     const events = await collectEvents(serverURL, traceId);
  51  |     if (events.some((e) => e.step_id === "run-summary")) return events;
  52  |     const done = new Set(
  53  |       events
  54  |         .filter((e) => e.step_id === "approval-resolved")
  55  |         .map((e) => String((e.payload as Record<string, unknown>)?.["approval_id"] ?? "")),
  56  |     );
  57  |     for (const e of events) {
  58  |       if (e.step_id !== "await-approval") continue;
  59  |       const aid = String((e.payload as Record<string, unknown>)?.["approval_id"] ?? "");
  60  |       if (!aid || done.has(aid) || resolved.has(aid)) continue;
  61  |       try {
  62  |         await fetch(`${serverURL}/api/runs/${runId}/approve`, {
  63  |           method: "POST",
  64  |           headers: { "Content-Type": "application/json" },
  65  |           body: JSON.stringify({ approval_id: aid, approved }),
  66  |         });
  67  |         resolved.add(aid);
  68  |       } catch {
  69  |         /* retry on next poll */
  70  |       }
  71  |     }
  72  |     await new Promise((r) => setTimeout(r, 500));
  73  |   }
  74  |   throw new Error("timed out draining approvals waiting for run-summary");
  75  | }
  76  | 
  77  | /**
  78  |  * Wait for run-summary, answering any pause prompt in the UI with
  79  |  * "Keep printing". Used by no-pause scenarios so a single unexpected prompt
  80  |  * surfaces as an assertion failure later, not a 120 s stall.
  81  |  */
  82  | export async function waitSummaryAnswering(
  83  |   page: Page,
  84  |   serverURL: string,
  85  |   traceId: string,
  86  |   timeoutMs = 110_000,
  87  | ): Promise<Envelope[]> {
  88  |   const start = Date.now();
  89  |   while (Date.now() - start < timeoutMs) {
  90  |     const dialog = page.getByRole("alertdialog");
  91  |     if ((await dialog.count()) > 0) {
  92  |       await page
  93  |         .getByRole("button", { name: "Keep printing" })
  94  |         .click({ timeout: 5_000 })
  95  |         .catch(() => {});
  96  |     }
  97  |     const events = await collectEvents(serverURL, traceId);
  98  |     if (events.some((e) => e.step_id === "run-summary")) return events;
  99  |     await page.waitForTimeout(1000);
  100 |   }
  101 |   throw new Error("timed out waiting for run-summary");
  102 | }
  103 | 
```