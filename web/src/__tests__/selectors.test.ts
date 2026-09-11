import { describe, expect, it } from "vitest";
import type { EventEnvelope } from "src/platform/transport";
import stepsJson from "../../../app/contracts/steps.json";
import {
  STEP_LABELS,
  selectDecisions,
  selectEvidenceUris,
  selectPendingApproval,
  selectScores,
  selectTraceRows,
} from "../selectors";

function env(
  seq: number,
  step_id: string,
  status: string,
  payload: Record<string, unknown>,
  trace_id = "r1",
): EventEnvelope {
  return {
    step_id,
    status: status as EventEnvelope["status"],
    payload: payload as EventEnvelope["payload"],
    timestamp: "2026-09-11T00:00:00Z",
    sequence: seq,
    trace_id: trace_id as EventEnvelope["trace_id"],
    degraded: false,
  } as EventEnvelope;
}

const scores = (frame: number) => ({
  frame_index: frame,
  t_ms: frame * 100,
  spaghetti_score: 0.1 + frame / 1000,
  confidence: 0.9,
});
const decision = (frame: number, action = "continue") => ({
  frame_index: frame,
  t_ms: frame * 100,
  action,
  reason_code: "nominal",
  spaghetti_score: 0.1,
  confidence: 0.9,
  threshold: 0.45,
  requires_human: false,
});

function fixture(): EventEnvelope[] {
  return [
    env(0, "run-start", "started", { run_id: "r1", source: "x", backend: "b", opencv_version: "5", cool_version: null, total_frames: null, synthetic: true }),
    env(1, "perceive", "done", { scores: scores(6) }),
    env(2, "perceive", "done", { scores: scores(3) }),
    env(3, "decide", "done", { decision: decision(3) }),
    env(4, "await-approval", "started", { approval_id: "a1", decision: decision(9, "request_pause_approval") }),
    env(5, "evidence-stored", "done", { uri: "/api/evidence/runs/r1/clip.mp4", kind: "clip", bytes: 10, backend: "local" }),
  ];
}

describe("selectors", () => {
  it("selectScores returns frame-sorted", () => {
    const s = selectScores(fixture(), "r1");
    expect(s.map((x) => x.frame_index)).toEqual([3, 6]);
  });

  it("pending approval before resolution, null after", () => {
    const before = selectPendingApproval(fixture(), "r1");
    expect(before?.approvalId).toBe("a1");
    const withResolve = [
      ...fixture(),
      env(6, "approval-resolved", "done", { approval_id: "a1", approved: true, resolved_by: "human", t_ms: 300 }),
    ];
    expect(selectPendingApproval(withResolve, "r1")).toBeNull();
  });

  it("trace rows zip and skip unmatched", () => {
    const rows = selectTraceRows(fixture(), "r1");
    expect(rows.length).toBe(1);
    expect(rows[0]!.frameIndex).toBe(3);
  });

  it("empty / malformed / foreign trace → empty", () => {
    expect(selectScores([], "r1")).toEqual([]);
    expect(selectDecisions([], "r1")).toEqual([]);
    expect(selectPendingApproval([], "r1")).toBeNull();
    expect(selectTraceRows([], "r1")).toEqual([]);
    const malformed = [env(0, "perceive", "done", { nope: 1 })];
    expect(selectScores(malformed, "r1")).toEqual([]);
    expect(selectScores(fixture(), "other")).toEqual([]);
    expect(selectEvidenceUris(fixture(), "other")).toEqual([]);
  });

  it("STEP_LABELS covers steps.json", () => {
    for (const id of (stepsJson as { steps: string[] }).steps) {
      expect(STEP_LABELS[id]).toBeTruthy();
    }
  });
});
