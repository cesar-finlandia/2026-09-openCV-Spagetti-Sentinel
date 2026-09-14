# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: scenarios\uc07-evidence-retrieval.spec.ts >> uc07 every stored evidence URI resolves; missing keys 404 honestly
- Location: e2e\scenarios\uc07-evidence-retrieval.spec.ts:10:1

# Error details

```
Error: expect(received).toMatch(expected)

Expected pattern: /^(video|image)\//
Received string:  "text/html; charset=utf-8"
```

# Page snapshot

```yaml
- generic [ref=e3]:
  - banner [ref=e4]:
    - generic [ref=e5]: Spaghetti Sentinel
    - generic [ref=e10]:
      - generic "baseline OpenCV backend" [ref=e11]:
        - generic [ref=e13]: baseline OpenCV 5.0.0
        - generic [ref=e14]: e2e-2026-09-13T20-32-11-466Z
      - 'status "stream status: connecting" [ref=e15]': connecting
      - switch "Switch to dark theme" [ref=e17] [cursor=pointer]
  - status "Starting the run — connecting to the live stream" [ref=e22]:
    - generic [ref=e25]:
      - generic [ref=e26]: Starting the run — connecting to the live stream
      - generic [ref=e27]: 43.0s
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
    - paragraph [ref=e87]: build e2e-2026-09-13T20-32-11-466Z
```

# Test source

```ts
  1  | // uc07 — the stored proof can actually be opened.
  2  | // NOTE (fix-log #4): playable embeds are proven in uc04; here the browser
  3  | // route aborts evidence files so the panel must render the honest
  4  | // "this clip could not be loaded" state, while node-fetch proves every
  5  | // stored URI independently resolves.
  6  | import { appTest, expect } from "../fixtures/app";
  7  | import { collectEvents } from "../fixtures/envelopes";
  8  | import { drainApprovals, startClipRun } from "../fixtures/runs";
  9  | 
  10 | appTest("uc07 every stored evidence URI resolves; missing keys 404 honestly", async ({
  11 |   page,
  12 |   serverURL,
  13 | }) => {
  14 |   await page.route("**/api/evidence/**", (route) => route.abort());
  15 |   await page.goto(`${serverURL}/`);
  16 |   // Evidence only materialises off replay (fix-log #12): real pipeline here.
  17 |   await page.getByLabel("Replay (offline)").uncheck();
  18 |   const traceId = await startClipRun(page, "spaghetti", "baseline");
  19 |   const events = await drainApprovals(serverURL, traceId, traceId, true);
  20 |   expect(events.some((e) => e.step_id === "run-summary")).toBe(true);
  21 | 
  22 |   const uris = [
  23 |     ...new Set(
  24 |       events
  25 |         .filter((e) => e.step_id === "evidence-stored")
  26 |         .map((e) => String((e.payload as Record<string, unknown>)?.["uri"] ?? ""))
  27 |         .filter((u) => u.length > 0),
  28 |     ),
  29 |   ];
  30 |   expect(uris.length).toBeGreaterThan(0);
  31 | 
  32 |   // Backend truth, unaffected by the browser route: every URI resolves with a
  33 |   // video/ or image/ content type.
  34 |   for (const uri of uris) {
  35 |     const url = uri.startsWith("s3://")
  36 |       ? uri // presigned-link path is asserted below, not fetched
  37 |       : uri.startsWith("http")
  38 |         ? uri
  39 |         : `${serverURL}/${uri.replace(/^\//, "")}`;
  40 |     if (uri.startsWith("s3://")) continue;
  41 |     const res = await fetch(url);
  42 |     expect(res.status, `GET ${uri}`).toBe(200);
  43 |     const ct = res.headers.get("content-type") ?? "";
> 44 |     expect(ct).toMatch(/^(video|image)\//);
     |                ^ Error: expect(received).toMatch(expected)
  45 |     await res.arrayBuffer();
  46 |   }
  47 | 
  48 |   // The panel, starved of its files by the aborted route, tells the truth.
  49 |   const evidence = page.locator('section[aria-label="Evidence"]');
  50 |   await expect(evidence.getByText(/this clip could not be loaded/).first()).toBeVisible({
  51 |     timeout: 30_000,
  52 |   });
  53 | 
  54 |   // One deliberate bad key returns 404.
  55 |   const bad = await fetch(`${serverURL}/api/evidence/definitely-missing-key.png`);
  56 |   expect(bad.status).toBe(404);
  57 |   void collectEvents;
  58 | });
  59 | 
```