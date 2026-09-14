# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: scenarios\uc05-vision-changes-action.spec.ts >> uc05 vision output changes the action, tools manifest, honest rationale
- Location: e2e\scenarios\uc05-vision-changes-action.spec.ts:6:1

# Error details

```
Error: expect(received).toEqual(expected) // deep equality

Expected: "request_pause_approval"
Received: "nudge_parameters"
```

# Page snapshot

```yaml
- generic [ref=e3]:
  - banner [ref=e4]:
    - generic [ref=e5]: Spaghetti Sentinel
    - generic [ref=e10]:
      - generic "baseline OpenCV backend" [ref=e11]:
        - generic [ref=e13]: baseline OpenCV 5.0.0
        - generic [ref=e14]: e2e-2026-09-13T20-31-42-986Z
      - 'status "stream status: connecting" [ref=e15]': connecting
      - switch "Switch to dark theme" [ref=e17] [cursor=pointer]
  - status "Starting the run — connecting to the live stream" [ref=e22]:
    - generic [ref=e25]:
      - generic [ref=e26]: Starting the run — connecting to the live stream
      - generic [ref=e27]: 22.3s
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
    - paragraph [ref=e87]: build e2e-2026-09-13T20-31-42-986Z
```

# Test source

```ts
  1  | // uc05 — mandatory technology: Agentic Vision. The vision number, not a
  2  | // chatbot, changes what the system does.
  3  | import { appTest, expect } from "../fixtures/app";
  4  | import { drainApprovals, startClipRun } from "../fixtures/runs";
  5  | 
  6  | appTest("uc05 vision output changes the action, tools manifest, honest rationale", async ({
  7  |   page,
  8  |   serverURL,
  9  | }) => {
  10 |   // Exactly 4 tools with JSON schemas — the artefact of the real registry.
  11 |   const toolsRes = await fetch(`${serverURL}/api/tools`);
  12 |   expect(toolsRes.ok).toBe(true);
  13 |   const tools = (await toolsRes.json()) as {
  14 |     name: string;
  15 |     input_schema: { type?: string };
  16 |   }[];
  17 |   expect(Array.isArray(tools)).toBe(true);
  18 |   expect(tools).toHaveLength(4);
  19 |   const names = tools.map((t) => t.name).sort();
  20 |   expect(names).toContain("score_frame");
  21 |   for (const t of tools) {
  22 |     expect(t.input_schema?.type).toEqual("object");
  23 |   }
  24 | 
  25 |   await page.goto(`${serverURL}/`);
  26 |   const traceId = await startClipRun(page, "spaghetti", "baseline");
  27 |   const events = await drainApprovals(serverURL, traceId, traceId, true);
  28 | 
  29 |   // The manifest also renders in the UI trace card once the run exists.
  30 |   const traceCard = page.locator('section[aria-label="Decision trace"]');
  31 |   await expect(traceCard).toBeVisible();
  32 |   await expect(traceCard.getByText("Agent tools (4)")).toBeVisible();
  33 | 
  34 |   // Score-crosses-threshold ⟺ action flips, on the backend's own envelopes.
  35 |   const scores = new Map<number, number>();
  36 |   for (const e of events) {
  37 |     if (e.step_id !== "perceive" || e.status !== "done") continue;
  38 |     const s = e.payload?.["scores"] as Record<string, unknown>;
  39 |     scores.set(Number(s["frame_index"]), Number(s["spaghetti_score"]));
  40 |   }
  41 |   let threshold = 0.72;
  42 |   let checked = 0;
  43 |   for (const e of events) {
  44 |     if (e.step_id !== "decide" || e.status !== "done") continue;
  45 |     const d = e.payload?.["decision"] as Record<string, unknown>;
  46 |     if (d["degraded"] === true) continue;
  47 |     threshold = Number(d["threshold"] ?? threshold);
  48 |     const score = scores.get(Number(d["frame_index"]));
  49 |     if (score === undefined) continue;
  50 |     checked += 1;
  51 |     if (score >= threshold) {
> 52 |       expect(String(d["action"])).toEqual("request_pause_approval");
     |                                   ^ Error: expect(received).toEqual(expected) // deep equality
  53 |     } else {
  54 |       expect(String(d["action"])).not.toEqual("request_pause_approval");
  55 |     }
  56 |   }
  57 |   expect(checked).toBeGreaterThan(10);
  58 | 
  59 |   // Rationale exists only AFTER the first decide — never before the gate.
  60 |   const seqOf = (id: string) =>
  61 |     events.filter((e) => e.step_id === id).map((e) => e.sequence ?? 0);
  62 |   const firstDecide = Math.min(...seqOf("decide"));
  63 |   const rationales = seqOf("rationale");
  64 |   expect(rationales.length).toBeGreaterThan(0);
  65 |   expect(Math.min(...rationales)).toBeGreaterThan(firstDecide);
  66 | 
  67 |   // The chip tells the truth about the source.
  68 |   const firstAlert = events
  69 |     .filter((e) => e.step_id === "decide" && e.status === "done")
  70 |     .map((e) => e.payload?.["decision"] as Record<string, unknown>)
  71 |     .find((d) => d["action"] !== "continue");
  72 |   const source = String(firstAlert?.["rationale_source"] ?? "fallback");
  73 |   await expect(page.getByText(`rationale: ${source === "bedrock" ? "bedrock" : "measured fallback"}`).first()).toBeVisible();
  74 | });
  75 | 
```