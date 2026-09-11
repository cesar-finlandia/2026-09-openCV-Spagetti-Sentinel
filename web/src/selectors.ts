// Pure functions over EventEnvelope[]. No React, no fetch, no Date.now().
// These are the ONLY place payload keys are read, so a blueprint §2.3 change
// touches exactly one file.
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
};

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

export const STEP_LABELS: Record<string, string> = LABELS;

function inTrace(envelopes: EventEnvelope[], runId: string | null): EventEnvelope[] {
  if (!runId) return envelopes;
  return envelopes.filter((e) => !e.trace_id || e.trace_id === runId);
}

function isObj(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null;
}

export function selectRunHeader(
  envelopes: EventEnvelope[],
  runId: string | null = null,
): RunHeader {
  for (const e of inTrace(envelopes, runId)) {
    if (e.step_id === "run-start") {
      const p = isObj(e.payload) ? e.payload : {};
      return {
        runId: String(p["run_id"] ?? ""),
        source: String(p["source"] ?? ""),
        backend: String(p["backend"] ?? ""),
        opencvVersion: String(p["opencv_version"] ?? ""),
        coolVersion: (p["cool_version"] as string | null) ?? null,
        synthetic: Boolean(p["synthetic"]),
      };
    }
  }
  return null;
}

export function selectScores(
  envelopes: EventEnvelope[],
  runId: string | null = null,
): VisionScores[] {
  const out: VisionScores[] = [];
  for (const e of inTrace(envelopes, runId)) {
    if (e.step_id === "perceive" && e.status === "done" && isObj(e.payload)) {
      const s = e.payload["scores"];
      if (isObj(s) && typeof s["frame_index"] === "number") {
        out.push(s as unknown as VisionScores);
      }
    }
  }
  out.sort((a, b) => a.frame_index - b.frame_index);
  return out;
}

export function selectDecisions(
  envelopes: EventEnvelope[],
  runId: string | null = null,
): AgentDecision[] {
  const out: AgentDecision[] = [];
  for (const e of inTrace(envelopes, runId)) {
    if (e.step_id === "decide" && e.status === "done" && isObj(e.payload)) {
      const d = e.payload["decision"];
      if (isObj(d) && typeof d["frame_index"] === "number") {
        out.push(d as unknown as AgentDecision);
      }
    }
  }
  out.sort((a, b) => a.frame_index - b.frame_index);
  return out;
}

export function selectLatestDecision(
  envelopes: EventEnvelope[],
  runId: string | null = null,
): AgentDecision | null {
  const ds = selectDecisions(envelopes, runId);
  return ds.length ? ds[ds.length - 1]! : null;
}

export function selectPendingApproval(
  envelopes: EventEnvelope[],
  runId: string | null = null,
): PendingApproval {
  const scoped = inTrace(envelopes, runId);
  for (let i = scoped.length - 1; i >= 0; i--) {
    const e = scoped[i]!;
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

export function selectEvidenceUris(
  envelopes: EventEnvelope[],
  runId: string | null = null,
): string[] {
  const out: string[] = [];
  for (const e of inTrace(envelopes, runId)) {
    if (e.step_id === "evidence-stored" && isObj(e.payload)) {
      const u = e.payload["uri"];
      if (typeof u === "string" && u) out.push(u);
    }
  }
  return out;
}

export function selectSummary(
  envelopes: EventEnvelope[],
  runId: string | null = null,
): Record<string, unknown> | null {
  const scoped = inTrace(envelopes, runId);
  for (let i = scoped.length - 1; i >= 0; i--) {
    const e = scoped[i]!;
    if (e.step_id === "run-summary" && isObj(e.payload) && isObj(e.payload["summary"])) {
      return e.payload["summary"] as Record<string, unknown>;
    }
  }
  return null;
}

export function selectTraceRows(
  envelopes: EventEnvelope[],
  runId: string | null = null,
): TraceRow[] {
  const scores = selectScores(envelopes, runId);
  const decisions = selectDecisions(envelopes, runId);
  const byFrame = new Map<number, AgentDecision>();
  for (const d of decisions) byFrame.set(d.frame_index, d);
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
    });
  }
  return rows;
}

export function selectDegradedReasons(
  envelopes: EventEnvelope[],
  runId: string | null = null,
): string[] {
  const out: string[] = [];
  for (const e of inTrace(envelopes, runId)) {
    if (isDegradedEnvelope(e)) {
      const r = degradedResultOf(e)?.reason || e.step_id;
      if (!out.includes(r)) out.push(r);
    }
  }
  return out;
}
