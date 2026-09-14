// Backend-truth helpers: read envelopes over HTTP and wait for run steps.
// Scenarios never waitForTimeout; they waitForStep instead.
import type { Page } from "@playwright/test";

export type Envelope = {
  step_id: string;
  status: string;
  trace_id?: string;
  sequence?: number;
  payload?: Record<string, unknown>;
  degraded?: boolean;
};

export async function collectEvents(
  baseURL: string,
  traceId: string,
): Promise<Envelope[]> {
  const res = await fetch(
    `${baseURL}/events?trace_id=${encodeURIComponent(traceId)}`,
  );
  if (!res.ok) throw new Error(`GET /events -> ${res.status}`);
  const body = (await res.json()) as { events?: Envelope[] };
  return body.events ?? [];
}

export async function waitForStep(
  page: Page,
  baseURL: string,
  traceId: string,
  stepId: string,
  timeoutMs = 100_000,
): Promise<Envelope[]> {
  const start = Date.now();
  let seen: string[] = [];
  while (Date.now() - start < timeoutMs) {
    const events = await collectEvents(baseURL, traceId);
    seen = [...new Set(events.map((e) => e.step_id))];
    if (
      events.some((e) => e.step_id === stepId && e.status !== "started")
    ) {
      return events;
    }
    await page.waitForTimeout(1000);
  }
  throw new Error(
    `timed out waiting for step ${stepId}; steps seen: ${seen.join(", ")}`,
  );
}

export function payload<T>(e: Envelope | undefined): T {
  return ((e?.payload ?? {}) as T) ?? ({} as T);
}
