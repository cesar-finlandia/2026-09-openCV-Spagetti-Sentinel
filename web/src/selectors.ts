// Pure functions over EventEnvelope[]. No React, no fetch, no Date.now().
// These are the ONLY place payload keys are read, so a blueprint §2.3 change
// touches exactly one file.
//
// NOTE on the §5.1 cross-talk guard: these selectors are single-argument and
// operate on the array they are given. App.tsx applies the guard once —
// envelopes.filter((e) => !runId || e.trace_id === runId) — before calling
// any selector, so every view-model below is already trace-scoped.
import type { EventEnvelope } from "src/platform/transport";
import { degradedResultOf, isDegradedEnvelope } from "src/platform/ui";
import stepsJson from "../../app/contracts/steps.json";

export type VisionScores = {
  frame_index: number;
  t_ms: number;
  first_layer_coverage: number;
  edge_regularity: number;
  motion_energy: number;
  texture_disorder: number;
  spaghetti_score: number;
  confidence: number;
  roi: number[];
  backend: "cool" | "baseline";
  ops_ms: Record<string, number>;
  degraded: boolean;
};

export type AgentDecision = {
  frame_index: number;
  t_ms: number;
  action: "continue" | "nudge_parameters" | "capture_evidence" | "request_pause_approval";
  reason_code: string;
  spaghetti_score: number;
  confidence: number;
  threshold: number;
  requires_human: boolean;
  rationale: string;
  checklist: string[];
  evidence_uri: string | null;
  rationale_source: "bedrock" | "fallback";
  degraded: boolean;
};

export type PendingApproval = { approvalId: string; decision: AgentDecision } | null;

export type RunHeader = {
  runId: string;
  source: string;
  backend: string;
  opencvVersion: string;
  coolVersion: string | null;
  synthetic: boolean;
  totalFrames: number | null;
} | null;

export type TraceRow = {
  sequence: number;
  tMs: number;
  frameIndex: number;
  spaghettiScore: number;
  confidence: number;
  threshold: number;
  action: string;
  reasonCode: string;
  requiresHuman: boolean;
  degraded: boolean;
};

/** What WorkIndicator says right now. */
export type ActivityLine = { stepId: string; text: string; done: boolean };

export const PAUSE_THRESHOLD_FALLBACK = 0.62;
export const APPROVAL_TIMEOUT_S = 120;

const LABELS: Record<string, string> = {
  "run-start": "Starting",
  ingest: "Reading frames",
  perceive: "OpenCV 5 analysis",
  decide: "Decision",
  act: "Action",
  "await-approval": "Waiting for you",
  "approval-resolved": "You answered",
  "evidence-stored": "Evidence saved",
  rationale: "Explanation",
  "run-summary": "Finished",
};

for (const id of (stepsJson as { steps: string[] }).steps) {
  if (!(id in LABELS)) {
    throw new Error(`selectors: missing STEP_LABELS entry for step id "${id}"`);
  }
}

/** step_id -> human label, passed to the chassis StepStatusIndicator's labelMap prop. */
export const STEP_LABELS: Record<string, string> = LABELS;

function isObj(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null;
}

export function selectRunHeader(envelopes: EventEnvelope[]): RunHeader {
  for (const e of envelopes) {
    if (e.step_id === "run-start") {
      const p = isObj(e.payload) ? e.payload : {};
      const total = p["total_frames"];
      return {
        runId: String(p["run_id"] ?? ""),
        source: String(p["source"] ?? ""),
        backend: String(p["backend"] ?? ""),
        opencvVersion: String(p["opencv_version"] ?? ""),
        coolVersion: (p["cool_version"] as string | null) ?? null,
        synthetic: Boolean(p["synthetic"]),
        totalFrames: typeof total === "number" ? total : null,
      };
    }
  }
  return null;
}

export function selectScores(envelopes: EventEnvelope[]): VisionScores[] {
  const out: VisionScores[] = [];
  for (const e of envelopes) {
    if (e.step_id === "perceive" && e.status === "done" && isObj(e.payload)) {
      const s = e.payload["scores"];
      if (isObj(s)) out.push(s as unknown as VisionScores);
    }
  }
  out.sort((a, b) => a.frame_index - b.frame_index);
  return out;
}

export function selectDecisions(envelopes: EventEnvelope[]): AgentDecision[] {
  const out: AgentDecision[] = [];
  for (const e of envelopes) {
    if (e.step_id === "decide" && e.status === "done" && isObj(e.payload)) {
      const d = e.payload["decision"];
      if (isObj(d)) out.push(d as unknown as AgentDecision);
    }
  }
  out.sort((a, b) => a.frame_index - b.frame_index);
  return out;
}

export function selectLatestDecision(envelopes: EventEnvelope[]): AgentDecision | null {
  const ds = selectDecisions(envelopes);
  return ds.length ? ds[ds.length - 1]! : null;
}

export function selectPendingApproval(envelopes: EventEnvelope[]): PendingApproval {
  for (let i = envelopes.length - 1; i >= 0; i--) {
    const e = envelopes[i]!;
    if (e.step_id === "approval-resolved") return null;
    if (e.step_id === "await-approval" && isObj(e.payload)) {
      const d = e.payload["decision"];
      if (isObj(d)) {
        return {
          approvalId: String(e.payload["approval_id"] ?? ""),
          decision: d as unknown as AgentDecision,
        };
      }
    }
  }
  return null;
}

export function selectEvidenceUris(envelopes: EventEnvelope[]): string[] {
  const out: string[] = [];
  for (const e of envelopes) {
    if (e.step_id === "evidence-stored" && isObj(e.payload)) {
      const u = e.payload["uri"];
      if (typeof u === "string" && u && !out.includes(u)) out.push(u);
    }
  }
  return out;
}

export function selectSummary(envelopes: EventEnvelope[]): Record<string, unknown> | null {
  for (let i = envelopes.length - 1; i >= 0; i--) {
    const e = envelopes[i]!;
    if (e.step_id === "run-summary" && isObj(e.payload) && isObj(e.payload["summary"])) {
      return e.payload["summary"] as Record<string, unknown>;
    }
  }
  return null;
}

export function selectTraceRows(envelopes: EventEnvelope[]): TraceRow[] {
  const scores = selectScores(envelopes);
  const byFrame = new Map<number, AgentDecision>();
  for (const d of selectDecisions(envelopes)) byFrame.set(d.frame_index, d);
  const rows: TraceRow[] = [];
  let seq = 0;
  for (const s of scores) {
    const d = byFrame.get(s.frame_index);
    if (!d) continue;
    rows.push({
      sequence: seq++,
      tMs: s.t_ms,
      frameIndex: s.frame_index,
      spaghettiScore: s.spaghetti_score,
      confidence: s.confidence,
      threshold: d.threshold,
      action: d.action,
      reasonCode: d.reason_code,
      requiresHuman: d.requires_human,
      degraded: Boolean(s.degraded) || Boolean(d.degraded),
    });
  }
  return rows;
}

export function selectDegradedReasons(envelopes: EventEnvelope[]): string[] {
  const out: string[] = [];
  for (const e of envelopes) {
    if (isDegradedEnvelope(e)) {
      const r = degradedResultOf(e)?.reason || e.step_id;
      if (!out.includes(r)) out.push(r);
    }
  }
  return out;
}

export function selectActivityLine(envelopes: EventEnvelope[]): ActivityLine {
  if (envelopes.length === 0) {
    return {
      stepId: "run-start",
      text: "Starting the run — connecting to the live stream",
      done: false,
    };
  }
  let top = envelopes[0]!;
  for (const e of envelopes) {
    if ((e.sequence ?? 0) >= (top.sequence ?? 0)) top = e;
  }
  const p = isObj(top.payload) ? top.payload : {};
  const header = selectRunHeader(envelopes);
  switch (top.step_id) {
    case "run-start":
      return { stepId: top.step_id, text: "Starting the run — connecting to the live stream", done: false };
    case "ingest": {
      const frame = typeof p["frame_index"] === "number" ? p["frame_index"] : "?";
      const total = header?.totalFrames ?? "?";
      return { stepId: top.step_id, text: `Reading frames — frame ${frame} of ${total}`, done: false };
    }
    case "perceive": {
      const s = isObj(p["scores"]) ? p["scores"] : {};
      const frame = typeof s["frame_index"] === "number" ? s["frame_index"] : "?";
      return { stepId: top.step_id, text: `OpenCV 5 analysis — frame ${frame}`, done: false };
    }
    case "decide":
      return { stepId: top.step_id, text: "Deciding what to do", done: false };
    case "act":
      return { stepId: top.step_id, text: "Acting on the decision", done: false };
    case "await-approval":
      return { stepId: top.step_id, text: "Waiting for you to answer", done: false };
    case "approval-resolved":
      return { stepId: top.step_id, text: "You answered — carrying on", done: false };
    case "evidence-stored":
      return { stepId: top.step_id, text: "Saving evidence to S3", done: false };
    case "rationale":
      return { stepId: top.step_id, text: "Writing the explanation", done: false };
    case "run-summary":
      return { stepId: top.step_id, text: "Finished", done: top.status === "done" };
    default:
      return { stepId: top.step_id, text: "Starting the run — connecting to the live stream", done: false };
  }
}
