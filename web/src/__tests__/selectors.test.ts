import { describe, expect, it } from "vitest";
import type { EventEnvelope } from "src/platform/transport";
import stepsJson from "../../../app/contracts/steps.json";
import {
  APPROVAL_TIMEOUT_S,
  PAUSE_THRESHOLD_FALLBACK,
  STEP_LABELS,
  selectActivityLine,
  selectDecisions,
  selectDegradedReasons,
  selectEvidenceUris,
  selectLatestDecision,
  selectPendingApproval,
  selectRunHeader,
  selectScores,
  selectSummary,
  selectTraceRows,
} from "../selectors";

function env(
  seq: number,
  step_id: string,
  status: string,
  payload: unknown,
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

const scores = (frame: number, extra: Record<string, unknown> = {}) => ({
  frame_index: frame,
  t_ms: frame * 100,
  spaghetti_score: 0.1 + frame / 1000,
  confidence: 0.9,
  degraded: false,
  ...extra,
});
const decision = (frame: number, action = "continue", extra: Record<string, unknown> = {}) => ({
  frame_index: frame,
  t_ms: frame * 100,
  action,
  reason_code: "nominal",
  spaghetti_score: 0.1,
  confidence: 0.9,
  threshold: 0.45,
  requires_human: action === "request_pause_approval",
  rationale: "r",
  checklist: ["c1"],
  evidence_uri: null,
  rationale_source: "fallback",
  degraded: false,
  ...extra,
});

function fixture(): EventEnvelope[] {
  return [
    env(0, "run-start", "started", {
      run_id: "r1", source: "x", backend: "b", opencv_version: "5",
      cool_version: null, total_frames: null, synthetic: true,
    }),
    env(1, "perceive", "done", { scores: scores(6) }),
    env(2, "perceive", "done", { scores: scores(3) }),
    env(3, "decide", "done", { decision: decision(3) }),
    env(4, "decide", "done", { decision: decision(9, "request_pause_approval") }),
    env(5, "await-approval", "started", { approval_id: "a1", decision: decision(9, "request_pause_approval") }),
    env(6, "evidence-stored", "done", { uri: "/api/evidence/runs/r1/clip.mp4" }),
  ];
}

describe("selectors", () => {
  it("selectScores returns frame-sorted scores", () => {
    const got = selectScores(fixture()).map((s) => s.frame_index);
    expect(got).toEqual([3, 6]);
  });

  it("approval state machine resolves in both directions", () => {
    const f = fixture();
    const pending = selectPendingApproval(f);
    expect(pending?.approvalId).toBe("a1");
    const resolved = [...f, env(7, "approval-resolved", "done", { approval_id: "a1", approved: true })];
    expect(selectPendingApproval(resolved)).toBeNull();
    const again = [...resolved, env(8, "await-approval", "started", { approval_id: "a2", decision: decision(12) })];
    expect(selectPendingApproval(again)?.approvalId).toBe("a2");
  });

  it("selectTraceRows zips on frame_index and skips an unmatched score", () => {
    const rows = selectTraceRows(fixture());
    expect(rows.map((r) => r.frameIndex)).toEqual([3]);
    expect(rows[0]).toMatchObject({ sequence: 0, action: "continue", degraded: false });
  });

  it("selectTraceRows ORs score and decision degraded flags", () => {
    const f = fixture();
    f[1] = env(1, "perceive", "done", { scores: scores(3, { degraded: true }) });
    const rows = selectTraceRows(f);
    expect(rows.find((r) => r.frameIndex === 3)?.degraded).toBe(true);
  });

  it("returns []/null for empty and malformed envelopes", () => {
    expect(selectScores([])).toEqual([]);
    expect(selectDecisions([])).toEqual([]);
    expect(selectLatestDecision([])).toBeNull();
    expect(selectPendingApproval([])).toBeNull();
    expect(selectRunHeader([])).toBeNull();
    expect(selectSummary([])).toBeNull();
    expect(selectTraceRows([])).toEqual([]);
    expect(selectEvidenceUris([])).toEqual([]);
    const malformed = [
      env(0, "perceive", "done", null),
      env(1, "perceive", "done", { scores: "nope" }),
      env(2, "decide", "done", {}),
      env(3, "run-summary", "done", { summary: 42 }),
    ];
    expect(selectScores(malformed)).toEqual([]);
    expect(selectDecisions(malformed)).toEqual([]);
    expect(selectSummary(malformed)).toBeNull();
  });

  it("the §5.1 trace filter drops foreign-trace envelopes before selection", () => {
    const runId = "r1";
    const mixed = [...fixture(), env(9, "perceive", "done", { scores: scores(99) }, "other-run")];
    const scoped = mixed.filter((e) => !runId || e.trace_id === runId);
    expect(selectScores(scoped).map((s) => s.frame_index)).toEqual([3, 6]);
  });

  it("STEP_LABELS covers every id in steps.json", () => {
    for (const id of (stepsJson as { steps: string[] }).steps) {
      expect(STEP_LABELS[id]).toBeTruthy();
    }
  });

  it("selectRunHeader maps total_frames", () => {
    expect(selectRunHeader(fixture())?.totalFrames).toBeNull();
    const withTotal = [env(0, "run-start", "started", {
      run_id: "r1", source: "s", backend: "b", opencv_version: "5",
      cool_version: null, total_frames: 300, synthetic: false,
    })];
    expect(selectRunHeader(withTotal)?.totalFrames).toBe(300);
  });

  it("selectActivityLine returns the literal string for each step id", () => {
    expect(selectActivityLine([])).toEqual({
      stepId: "run-start",
      text: "Starting the run — connecting to the live stream",
      done: false,
    });
    const line = (step: string, payload: unknown = {}, status = "done", seq = 5) =>
      selectActivityLine([
        env(0, "run-start", "started", { run_id: "r1", total_frames: 300 }),
        env(seq, step, status, payload),
      ]).text;
    expect(line("run-start", {}, "started")).toBe("Starting the run — connecting to the live stream");
    expect(line("ingest", { frame_index: 7 })).toBe("Reading frames — frame 7 of 300");
    expect(line("perceive", { scores: { frame_index: 11 } })).toBe("OpenCV 5 analysis — frame 11");
    expect(line("decide")).toBe("Deciding what to do");
    expect(line("act")).toBe("Acting on the decision");
    expect(line("await-approval")).toBe("Waiting for you to answer");
    expect(line("approval-resolved")).toBe("You answered — carrying on");
    expect(line("evidence-stored")).toBe("Saving evidence to S3");
    expect(line("rationale")).toBe("Writing the explanation");
    expect(line("run-summary")).toBe("Finished");
    expect(selectActivityLine([env(0, "run-summary", "done", {})]).done).toBe(true);
    expect(selectActivityLine([env(0, "run-summary", "error", {})]).done).toBe(false);
  });

  it("selectEvidenceUris de-duplicates in order and selectDegradedReasons dedupes", () => {
    const f = fixture();
    const dup = [...f, env(7, "evidence-stored", "done", { uri: "/api/evidence/runs/r1/clip.mp4" })];
    expect(selectEvidenceUris(dup)).toEqual(["/api/evidence/runs/r1/clip.mp4"]);
    expect(selectDegradedReasons(f)).toEqual([]);
  });

  it("exports the frozen fallback constants", () => {
    expect(PAUSE_THRESHOLD_FALLBACK).toBe(0.62);
    expect(APPROVAL_TIMEOUT_S).toBe(120);
  });
});
