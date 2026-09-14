# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: scenarios\uc02-spaghetti-escalation.spec.ts >> uc02 spaghetti run escalates to a human pause approval
- Location: e2e\scenarios\uc02-spaghetti-escalation.spec.ts:6:1

# Error details

```
Error: expect(received).toBeGreaterThanOrEqual(expected)

Expected: >= NaN
Received:    0.78
```

# Page snapshot

```yaml
- generic [ref=e3]:
  - banner [ref=e4]:
    - generic [ref=e5]: Spaghetti Sentinel
    - generic [ref=e10]:
      - generic "baseline OpenCV backend" [ref=e11]:
        - generic [ref=e13]: baseline OpenCV 5.0.0
        - generic [ref=e14]: e2e-2026-09-13T20-30-31-266Z
      - 'status "stream status: connecting" [ref=e15]': connecting
      - switch "Switch to dark theme" [ref=e17] [cursor=pointer]
  - status "Starting the run — connecting to the live stream" [ref=e22]:
    - generic [ref=e25]:
      - generic [ref=e26]: Starting the run — connecting to the live stream
      - generic [ref=e27]: 3.9s
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
    - paragraph [ref=e87]: build e2e-2026-09-13T20-30-31-266Z
```

# Test source

```ts
  1  | // uc02 — the print fails and Maya is asked to approve a pause.
  2  | import { appTest, expect } from "../fixtures/app";
  3  | import { collectEvents } from "../fixtures/envelopes";
  4  | import { drainApprovals, startClipRun } from "../fixtures/runs";
  5  | 
  6  | appTest("uc02 spaghetti run escalates to a human pause approval", async ({
  7  |   page,
  8  |   serverURL,
  9  | }) => {
  10 |   await page.goto(`${serverURL}/`);
  11 |   const traceId = await startClipRun(page, "spaghetti", "baseline");
  12 | 
  13 |   // The work indicator proves the app is really working, not just painted.
  14 |   await expect(
  15 |     page.getByTestId("work-indicator-text"),
  16 |   ).not.toBeEmpty({ timeout: 30_000 });
  17 | 
  18 |   const dialog = page.getByRole("alertdialog");
  19 |   await expect(dialog).toBeVisible({ timeout: 90_000 });
  20 |   const sentence = await dialog.innerText();
  21 |   const m = sentence.match(/scored ([\d.]+)\s+against a threshold of ([\d.]+)/);
  22 |   expect(m, `dialog sentence quotes score and threshold: ${sentence}`).not.toBeNull();
> 23 |   expect(Number(m![1])).toBeGreaterThanOrEqual(Number(m![2]));
     |                         ^ Error: expect(received).toBeGreaterThanOrEqual(expected)
  24 | 
  25 |   await page.getByRole("button", { name: "Approve pause" }).click();
  26 |   // The approval resolves as approved:true on the backend …
  27 |   const start = Date.now();
  28 |   let resolved: { approved: boolean } | null = null;
  29 |   while (Date.now() - start < 30_000) {
  30 |     const events = await collectEvents(serverURL, traceId);
  31 |     const hit = events.filter((e) => e.step_id === "approval-resolved").pop();
  32 |     if (hit) {
  33 |       resolved = hit.payload as unknown as { approved: boolean };
  34 |       break;
  35 |     }
  36 |     await page.waitForTimeout(500);
  37 |   }
  38 |   expect(resolved, "an approval-resolved envelope exists").not.toBeNull();
  39 |   expect(resolved!.approved).toBe(true);
  40 |   // … and the panel unmounts.
  41 |   await expect(page.getByRole("alertdialog")).toHaveCount(0, { timeout: 15_000 });
  42 | 
  43 |   // Drain the remaining prompts over HTTP, then the run must complete and the
  44 |   // alert row must be highlighted in the trace.
  45 |   const events = await drainApprovals(serverURL, traceId, traceId, true);
  46 |   expect(events.some((e) => e.step_id === "run-summary")).toBe(true);
  47 |   const alertRows = page.locator("tr.row-alert");
  48 |   expect(await alertRows.count()).toBeGreaterThan(0);
  49 |   await expect(alertRows.first()).toContainText("request_pause_approval");
  50 | });
  51 | 
```