import { useEffect, useMemo, useRef, useState } from "react";
import { useEventStream } from "src/platform/transport";
import { setTheme } from "src/platform/ui";
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
  APPROVAL_TIMEOUT_S,
  PAUSE_THRESHOLD_FALLBACK,
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
} from "./selectors";
import { applyTheme, initialTheme, type ThemeId } from "./theme";
import { AppFooter } from "./components/AppFooter";
import { AppHeader } from "./components/AppHeader";
import { ApprovalPanel } from "./components/ApprovalPanel";
import { ConfidenceTimeline } from "./components/ConfidenceTimeline";
import { DecisionCard } from "./components/DecisionCard";
import { DegradedBanner } from "./components/DegradedBanner";
import { EvidencePanel } from "./components/EvidencePanel";
import { RunControls } from "./components/RunControls";
import { ScoreTiles } from "./components/ScoreTiles";
import { StepRail } from "./components/StepRail";
import { TraceView } from "./components/TraceView";
import { WorkIndicator } from "./components/WorkIndicator";

export function App() {
  const [runId, setRunId] = useState<string | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [fixtures, setFixtures] = useState<FixtureClip[]>([]);
  const [tools, setTools] = useState<ToolManifestEntry[]>([]);
  const [theme, setThemeId] = useState<ThemeId>("light");
  const [busy, setBusy] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const [approveError, setApproveError] = useState<string | null>(null);
  const [elapsedS, setElapsedS] = useState(0);
  const [stalledS, setStalledS] = useState<number | null>(null);
  const [remainingS, setRemainingS] = useState(APPROVAL_TIMEOUT_S);
  const [narrow, setNarrow] = useState(false);
  const [singleCol, setSingleCol] = useState(false);

  const runStartRef = useRef(0);
  const lastEnvelopeRef = useRef(0);
  const pendingSinceRef = useRef(0);

  const { envelopes, status, reconnect } = useEventStream(
    runId ? { url: "/events/stream", traceId: runId } : undefined,
  );

  useEffect(() => {
    const t = initialTheme();
    setThemeId(t);
    // Chassis first: setTheme("operator") sets data-theme="operator" as a
    // side effect, so applyTheme() must run after it — the stored
    // light/dark choice owns the attribute in the end (§5.5).
    setTheme("operator");
    applyTheme(t);
    getHealth().then(setHealth).catch(() => setHealth(null));
    getFixtures()
      .then((f) => setFixtures(f.clips))
      .catch(() => setFixtures([]));
    getTools()
      .then(setTools)
      .catch(() => setTools([]));
  }, []);

  useEffect(() => {
    const onResize = () => {
      setNarrow(window.innerWidth < 640);
      setSingleCol(window.innerWidth < 1024);
    };
    onResize();
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  // The §5.1 cross-talk guard, applied once: every selector below sees only
  // envelopes of the current run.
  const scoped = useMemo(
    () => envelopes.filter((e) => !runId || e.trace_id === runId),
    [envelopes, runId],
  );

  const header = useMemo(() => selectRunHeader(scoped), [scoped]);
  const scores = useMemo(() => selectScores(scoped), [scoped]);
  const decisions = useMemo(() => selectDecisions(scoped), [scoped]);
  const latest = useMemo(() => selectLatestDecision(scoped), [scoped]);
  const pending = useMemo(() => selectPendingApproval(scoped), [scoped]);
  const uris = useMemo(() => selectEvidenceUris(scoped), [scoped]);
  const rows = useMemo(() => selectTraceRows(scoped), [scoped]);
  const summary = useMemo(() => selectSummary(scoped), [scoped]);
  const reasons = useMemo(() => selectDegradedReasons(scoped), [scoped]);
  const line = useMemo(() => selectActivityLine(scoped), [scoped]);

  const running = runId !== null && summary === null;
  const threshold = latest?.threshold ?? PAUSE_THRESHOLD_FALLBACK;
  const showWork = runId !== null && !line.done;

  useEffect(() => {
    if (runId) {
      runStartRef.current = Date.now();
      lastEnvelopeRef.current = Date.now();
    }
  }, [runId]);

  useEffect(() => {
    if (scoped.length > 0) lastEnvelopeRef.current = Date.now();
  }, [scoped.length]);

  useEffect(() => {
    if (pending) {
      if (pendingSinceRef.current === 0) pendingSinceRef.current = Date.now();
    } else {
      pendingSinceRef.current = 0;
      setRemainingS(APPROVAL_TIMEOUT_S);
    }
  }, [pending]);

  useEffect(() => {
    if (!runId) return;
    const id = window.setInterval(() => {
      const now = Date.now();
      setElapsedS((now - runStartRef.current) / 1000);
      const quietS = (now - lastEnvelopeRef.current) / 1000;
      setStalledS(quietS > 8 ? quietS : null);
      if (pendingSinceRef.current > 0) {
        setRemainingS(Math.max(0, Math.round(APPROVAL_TIMEOUT_S - (now - pendingSinceRef.current) / 1000)));
      }
    }, 100);
    return () => window.clearInterval(id);
  }, [runId]);

  async function handleStart(req: StartRunRequest) {
    setBusy(true);
    setStartError(null);
    try {
      const r = await startRun(req);
      setElapsedS(0);
      setStalledS(null);
      setRunId(r.run_id);
    } catch (e) {
      setStartError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleUpload(file: File) {
    setBusy(true);
    setStartError(null);
    try {
      const r = await uploadRun(file);
      setElapsedS(0);
      setStalledS(null);
      setRunId(r.run_id);
    } catch (e) {
      setStartError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleAnswer(approved: boolean) {
    if (!pending || !runId) return;
    setApproveError(null);
    try {
      await approve(runId, pending.approvalId, approved);
    } catch (e) {
      setApproveError(e instanceof Error ? e.message : String(e));
    }
  }

  function handleThemeChange(t: ThemeId) {
    setThemeId(t);
    applyTheme(t);
  }

  const controls = (
    <RunControls
      fixtures={fixtures}
      disabled={busy || running}
      busy={busy}
      error={startError}
      collapsible={narrow}
      onStart={handleStart}
      onUpload={handleUpload}
    />
  );

  return (
    <div className="app">
      <AppHeader
        header={header}
        health={health}
        status={status}
        onReconnect={reconnect}
        theme={theme}
        onThemeChange={handleThemeChange}
      />

      <DegradedBanner reasons={reasons} />

      <ApprovalPanel
        pending={pending}
        onAnswer={handleAnswer}
        busy={false}
        error={approveError}
        remainingS={remainingS}
      />

      {showWork ? (
        <WorkIndicator
          active={status === "open" || status === "connecting"}
          line={line}
          elapsedS={elapsedS}
          stalledS={stalledS}
        />
      ) : null}

      {runId === null ? (
        <div className="empty-state">
          <h1 className="h1">Nothing is being watched yet.</h1>
          <p>Pick a demo clip and press &ldquo;Start watching&rdquo;. The whole run takes about 30 seconds.</p>
          {controls}
        </div>
      ) : (
        <>
          <div className="body-grid">
            <div className="col-main">
              <div className="order-scores">
                <ScoreTiles
                  latest={scores.length ? scores[scores.length - 1]! : null}
                  previous={scores.length > 1 ? scores[scores.length - 2]! : null}
                  threshold={threshold}
                />
              </div>
              <div className="order-timeline">
                <ConfidenceTimeline scores={scores} decisions={decisions} pauseThreshold={threshold} />
              </div>
              <div className="order-decision">
                <DecisionCard decision={latest} envelopes={scoped} />
              </div>
              <div className="order-evidence">
                <EvidencePanel uris={uris} />
              </div>
            </div>
            <div className="col-rail">
              <div className="order-controls">{controls}</div>
              <div className="order-steps">
                <StepRail envelopes={scoped} orientation={singleCol ? "horizontal" : "vertical"} />
              </div>
            </div>
          </div>
          <TraceView rows={rows} tools={tools} />
        </>
      )}

      <AppFooter header={header} health={health} />
    </div>
  );
}
