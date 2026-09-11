// Requirement IDs: XCUT-05, TRN-04, TRN-REU-01, MOCK-03 (format pointer only —
// M08 owns the real MOCK tests) | DP-B §10.7, §10.8 item 2
// Demo path: replays the MOCK-03 script fixture through the SAME publish
// primitive a real backend uses (`createPublisher().publish`), honoring
// delay_ms between emissions so the UI demo ticks through steps without any
// Engine backend. Envelope-centric single format per §11 row 6.9.
//
// Run: npm run mock:publish   (TRANSPORT=sse default; pair with `npm run dev`)
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { createPublisher } from "../src/platform/transport/index.js";
import type { Publisher } from "../src/platform/transport/index.js";
import type { EnvelopeStatus } from "../src/platform/transport/index.js";

type ScriptEntry = {
  envelope: {
    step_id: string;
    status: string;
    payload: Record<string, unknown>;
    timestamp: string;
    sequence: number;
    trace_id?: string;
    degraded?: boolean;
  };
  delay_ms: number;
};

const STATUSES: readonly EnvelopeStatus[] = ["started", "streaming", "done", "error"];

const fixturePath = fileURLToPath(
  new URL("../examples/dummy-fixtures/event-envelope/mock/example.json", import.meta.url),
);
const script: ScriptEntry[] = JSON.parse(readFileSync(fixturePath, "utf8"));

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function replay(publisher: Publisher): Promise<void> {
  for (const entry of script) {
    if (entry.delay_ms > 0) await sleep(entry.delay_ms);
    const e = entry.envelope;
    const status = (STATUSES as readonly string[]).includes(e.status)
      ? (e.status as EnvelopeStatus)
      : "started";
    // Same primitive as a real backend (TRN-04 indistinguishability §10.7):
    // publish() validates via RES-04 and assigns fresh sequence/timestamps.
    await publisher.publish({
      stepId: e.step_id,
      status,
      payload: e.payload ?? {},
      traceId: e.trace_id,
      degraded: e.degraded === true ? true : undefined,
    });
    console.info(`[mock:publish] ${e.step_id} ${status} (+${entry.delay_ms}ms)`);
  }
}

const publisher = createPublisher(process.env["TRANSPORT"] === "websocket" ? "websocket" : "sse");
try {
  await replay(publisher);
  console.info("[mock:publish] script complete");
} finally {
  await publisher.close();
}
