import { useEffect, useMemo, useState } from "react";
import { useEventStream } from "src/platform/transport";
import {
  CitationDisplay,
  StepStatusIndicator,
  setTheme,
} from "src/platform/ui";
import {
  approve,
  getFixtures,
  getHealth,
  getTools,
  startRun,
  uploadRun,
  type FixtureClip,
  type Health,
  type StartRunRequest,
  type ToolManifestEntry,
} from "./api";
import {
  STEP_LABELS,
  selectDecisions,
  selectDegradedReasons,
  selectEvidenceUris,
  selectLatestDecision,
  selectPendingApproval,
  selectRunHeader,
  selectScores,
  selectSummary,
  selectTraceRows,
} from "./selectors";
import { ApprovalPanel } from "./components/ApprovalPanel";
import { BackendBadge } from "./components/BackendBadge";
import { ConfidenceTimeline } from "./components/ConfidenceTimeline";
import { DecisionCard } from "./components/DecisionCard";
import { EvidencePanel } from "./components/EvidencePanel";
import { RunControls } from "./components/RunControls";
import { TraceView } from "./components/TraceView";

export function App() {
  const [runId, setRunId] = useState<string | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [fixtures, setFixtures] = useState<FixtureClip[]>([]);
  const [tools, setTools] = useState<ToolManifestEntry[]>([]);
  const [busy, setBusy] = useState(false);
  const [answerBusy, setAnswerBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { envelopes, status, degraded, reconnect } = useEventStream(
    runId ? { url: "/events/stream", traceId: runId } : undefined,
  );

  useEffect(() => {
    setTheme("operator");
    getHealth().then(setHealth).catch(() => setHealth(null));
    getFixtures()
      .then((f) => setFixtures(f.clips))
      .catch(() => setFixtures([]));
    getTools()
      .then(setTools)
      .catch(() => setTools([]));
  }, []);

  const scoped = useMemo(
    () => envelopes.filter((e) => !runId || !e.trace_id || e.trace_id === runId),
    [envelopes, runId],
  );
  const header = useMemo(() => selectRunHeader(scoped, runId), [scoped, runId]);
  const scores = useMemo(() => selectScores(scoped, runId), [scoped, runId]);
  const decisions = useMemo(() => selectDecisions(scoped, runId), [scoped, runId]);
  const latest = useMemo(() => selectLatestDecision(scoped, runId), [scoped, runId]);
  const pending = useMemo(() => selectPendingApproval(scoped, runId), [scoped, runId]);
  const uris = useMemo(() => selectEvidenceUris(scoped, runId), [scoped, runId]);
  const rows = useMemo(() => selectTraceRows(scoped, runId), [scoped, runId]);
  const summary = useMemo(() => selectSummary(scoped, runId), [scoped, runId]);
  const reasons = useMemo(() => selectDegradedReasons(scoped), [scoped]);

  const running = runId !== null && summary === null;

  async function handleStart(req: StartRunRequest) {
    setBusy(true);
    setError(null);
    try {
      const r = await startRun(req);
      setRunId(r.run_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleUpload(file: File) {
    setBusy(true);
    setError(null);
    try {
      const r = await uploadRun(file);
      setRunId(r.run_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleAnswer(approved: boolean) {
    if (!pending || !runId) return;
    setAnswerBusy(true);
    try {
      await approve(runId, pending.approvalId, approved);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setAnswerBusy(false);
    }
  }

  return (
    <div className="ss-shell">
      <header className="ss-row">
        <h1>Spaghetti Sentinel</h1>
        <BackendBadge header={header} health={health} />
        <span className="ss-muted">stream: {status}</span>
        {status === "error" ? <button className="ss-btn" onClick={reconnect}>Reconnect</button> : null}
      </header>

      {degraded ? (
        <div className="ss-card" role="status">
          Running degraded: {reasons.join(", ") || "see timeline"}
        </div>
      ) : null}
      {error ? (
        <div className="ss-card" role="alert">
          {error}
        </div>
      ) : null}

      <RunControls fixtures={fixtures} disabled={busy || running} onStart={handleStart} onUpload={handleUpload} />

      <StepStatusIndicator envelopes={scoped} labelMap={STEP_LABELS} title="Progress" />

      <ApprovalPanel pending={pending} onAnswer={handleAnswer} busy={answerBusy} />

      <ConfidenceTimeline scores={scores} decisions={decisions} pauseThreshold={0.72} />

      <DecisionCard decision={latest} envelopes={scoped} />

      <EvidencePanel uris={uris} />

      <TraceView rows={rows} tools={tools} />

      <footer className="ss-muted">
        {header?.synthetic ? <p>synthetic: true — generated demo footage, watermarked.</p> : null}
        <p>This system recommends; it never controls the printer.</p>
        {health ? <p>build: {health.build_marker}</p> : null}
        <CitationDisplay envelopes={scoped} title="Sources" />
      </footer>
    </div>
  );
}
