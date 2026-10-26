// uc07 — the stored proof can actually be opened.
// NOTE (fix-log #4): playable embeds are proven in uc04; here the browser
// route aborts evidence files so the panel must render the honest
// "this clip could not be loaded" state, while node-fetch proves every
// stored URI independently resolves.
import { appTest, expect } from "../fixtures/app";
import { collectEvents } from "../fixtures/envelopes";
import { drainApprovals, startClipRun } from "../fixtures/runs";

appTest("uc07 every stored evidence URI resolves; missing keys 404 honestly", async ({
  page,
  serverURL,
}) => {
  await page.route("**/api/evidence/**", (route) => route.abort());
  await page.goto(`${serverURL}/`);
  // Evidence only materialises off replay (fix-log #12): real pipeline here.
  await page.getByLabel("Replay (offline)").uncheck();
  const traceId = await startClipRun(page, "spaghetti", "baseline");
  const events = await drainApprovals(serverURL, traceId, traceId, true);
  expect(events.some((e) => e.step_id === "run-summary")).toBe(true);

  const uris = [
    ...new Set(
      events
        .filter((e) => e.step_id === "evidence-stored")
        .map((e) => String((e.payload as Record<string, unknown>)?.["uri"] ?? ""))
        .filter((u) => u.length > 0),
    ),
  ];
  expect(uris.length).toBeGreaterThan(0);

  // Backend truth, unaffected by the browser route: every stored URI has a
  // browser-openable form (file:// locals via /api/evidence/<key> — the same
  // mapping the UI's EvidencePanel applies) that resolves with a video/ or
  // image/ content type.
  const fetchable = (uri: string): string | null => {
    if (uri.startsWith("s3://")) return null;
    if (/^https?:\/\//.test(uri)) return uri;
    const norm = uri.replace(/\\/g, "/");
    const i = norm.indexOf("runs/");
    if (i >= 0) return `${serverURL}/api/evidence/${norm.slice(i)}`;
    return `${serverURL}/${norm.replace(/^\w+:\/+/, "")}`;
  };
  for (const uri of uris) {
    const url = fetchable(uri);
    if (url === null) continue; // s3 presigned-link path (not this backend)
    const res = await fetch(url);
    expect(res.status, `GET ${uri}`).toBe(200);
    const ct = res.headers.get("content-type") ?? "";
    expect(ct).toMatch(/^(video|image)\//);
    await res.arrayBuffer();
  }

  // The panel, starved of its files by the aborted route, tells the truth.
  const evidence = page.locator('section[aria-label="Evidence"]');
  await expect(evidence.getByText(/this clip could not be loaded/).first()).toBeVisible({
    timeout: 30_000,
  });

  // One deliberate bad key returns 404.
  const bad = await fetch(`${serverURL}/api/evidence/definitely-missing-key.png`);
  expect(bad.status).toBe(404);
  void collectEvents;
});
