import { useMemo } from "react";
import type { AgentDecision, VisionScores } from "../selectors";

export type ConfidenceTimelineProps = {
  scores: VisionScores[];
  decisions: AgentDecision[];
  pauseThreshold: number;
  height?: number;
};

export function ConfidenceTimeline(props: ConfidenceTimelineProps) {
  const { scores, decisions, pauseThreshold, height = 160 } = props;
  const H = height;
  const W = 1000;
  const body = useMemo(() => {
    if (scores.length < 2) return null;
    const first = scores[0]!.frame_index;
    const last = scores[scores.length - 1]!.frame_index;
    const span = Math.max(1, last - first);
    const x = (f: number) => ((f - first) / span) * (W - 60) + 30;
    const y = (v: number) => H - 12 - Math.min(1, Math.max(0, v)) * (H - 24);
    const conf = scores.map((s) => `${x(s.frame_index).toFixed(1)},${y(s.confidence).toFixed(1)}`).join(" ");
    const spag = scores.map((s) => `${x(s.frame_index).toFixed(1)},${y(s.spaghetti_score).toFixed(1)}`).join(" ");
    const alerts = decisions.filter((d) => d.action !== "continue");
    const byFrame = new Map(scores.map((s) => [s.frame_index, s] as const));
    return { conf, spag, alerts, byFrame, x, y };
  }, [scores, decisions, H]);

  if (!body) {
    return (
      <div className="ss-card">
        <h3 data-beat="timeline-title">Confidence timeline — risk score against the pause threshold</h3>
        <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{ width: "100%", height: H }}>
          <line x1="0" y1={H - 12} x2={W} y2={H - 12} stroke="var(--ss-line)" strokeDasharray="4 4" />
          <text x={W / 2} y={H / 2} textAnchor="middle" fill="var(--ss-muted)" fontSize="16">
            Waiting for the first measurements…
          </text>
        </svg>
      </div>
    );
  }
  const yT = H - 12 - Math.min(1, Math.max(0, pauseThreshold)) * (H - 24);
  return (
    <div className="ss-card">
      <h3 data-beat="timeline-title">Confidence timeline — risk score against the pause threshold</h3>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{ width: "100%", height: H }} role="img">
        <line x1="30" y1={yT} x2={W - 30} y2={yT} stroke="var(--ss-amber)" strokeDasharray="6 4" strokeWidth="1.5" />
        <text x={W - 28} y={yT - 4} textAnchor="end" fill="var(--ss-amber)" fontSize="13">
          pause threshold
        </text>
        <polyline points={body.conf} fill="none" stroke="var(--ss-muted)" strokeWidth="1.5" />
        <polyline points={body.spag} fill="none" stroke="var(--ss-verdigris)" strokeWidth="2.5" />
        {body.alerts.map((d, i) => {
          const s = body.byFrame.get(d.frame_index);
          if (!s) return null;
          const fill = d.action === "request_pause_approval" ? "var(--ss-amber)" : "var(--ss-verdigris)";
          return (
            <circle key={i} cx={body.x(d.frame_index)} cy={body.y(s.spaghetti_score)} r="5" fill={fill}>
              <title>{`${d.action} — ${d.reason_code}`}</title>
            </circle>
          );
        })}
        {scores
          .filter((s) => s.degraded)
          .map((s, i) => (
            <circle
              key={`d${i}`}
              cx={body.x(s.frame_index)}
              cy={body.y(s.spaghetti_score)}
              r="3"
              fill="none"
              stroke="var(--ss-degraded)"
            />
          ))}
      </svg>
    </div>
  );
}
