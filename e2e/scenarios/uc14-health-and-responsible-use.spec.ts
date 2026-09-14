// uc14 — the submission gate items are live.
import { appTest, expect } from "../fixtures/app";

appTest("uc14 health endpoint and responsible-use footer", async ({
  page,
  serverURL,
}) => {
  const healthRes = await fetch(`${serverURL}/healthz`);
  expect(healthRes.ok).toBe(true);
  const health = (await healthRes.json()) as {
    build_marker?: string;
    status?: string;
  };
  expect(health.build_marker ?? "").not.toEqual("");

  await page.goto(`${serverURL}/`);
  await expect(
    page.getByRole("button", { name: "Start watching" }),
  ).toBeVisible();

  const footer = page.getByRole("contentinfo");
  await expect(footer).toContainText(
    "This system recommends; it never controls the printer.",
  );
  await expect(footer).toContainText(`build ${health.build_marker}`);

  // The synthetic notice appears once a run header says synthetic: true.
  await page.getByLabel("Demo clip", { exact: true }).selectOption("good-first-layer");
  const [runRes] = await Promise.all([
    page.waitForResponse(
      (r) => r.url().includes("/api/runs") && r.request().method() === "POST",
    ),
    page.getByRole("button", { name: "Start watching" }).click(),
  ]);
  const started = (await runRes.json()) as { run_id: string };
  expect(started.run_id ?? "").not.toEqual("");
  // run-start envelope arrives within seconds; the notice follows it.
  await expect(footer).toContainText("Demo footage is synthetic", {
    timeout: 30_000,
  });
});
