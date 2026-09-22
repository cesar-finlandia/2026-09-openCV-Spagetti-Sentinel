import { useMemo, type JSX } from "react";
import type { AgentDecision, VisionScores } from "../selectors";

export type ConfidenceTimelineProps = {
  scores: VisionScores[];
  decisions: AgentDecision[];
  pauseThreshold: number;
  height?: number;
};

const W = 1000;
const PAD = 16;

function pathFor(values: { x: number; y: number }[]): string {
  return values.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
}

export function ConfidenceTimeline({ scores, decisions, pauseThreshold, height = 260 }: ConfidenceTimelineProps): JSX.Element {
  const H = height;
  const model = useMemo(() => {
    if (scores.length < 2) return null;
    const first = scores[0]!.frame_index;
    const last = scores[scores.length - 1]!.frame_index;
    const span = Math.max(1, last - first);
    const x = (f: number) => PAD + ((f - first) / span) * (W - PAD * 2);
    const y = (v: number) => H - PAD - Math.min(1, Math.max(0, v)) * (H - PAD * 2);
    const byFrame = new Map<number, AgentDecision>();
    for (const d of decisions) byFrame.set(d.frame_index, d);
    return {
      x,
      y,
      conf: pathFor(scores.map((s) => ({ x: x(s.frame_index), y: y(s.confidence) }))),
      spag: pathFor(scores.map((s) => ({ x: x(s.frame_index), y: y(s.spaghetti_score) }))),
      thresholdY: y(pauseThreshold),
      markers: decisions
        .filter((d) => d.action !== "continue")
        .map((d) => {
          const s = scores.find((v) => v.frame_index === d.frame_index);
          return { d, cx: x(d.frame_index), cy: y(s ? s.spaghetti_score : d.spaghetti_score) };
        }),
      degraded: scores.filter((s) => s.degraded).map((s) => ({ cx: x(s.frame_index), cy: y(s.spaghetti_score) })),
    };
  }, [scores.length]); // eslint-disable-line react-hooks/exhaustive-deps

  const hasDegraded = (model?.degraded.length ?? 0) > 0;
  const peak = scores.reduce((m, s) => Math.max(m, s.spaghetti_score), 0);
  const alerts = decisions.filter((d) => d.action !== "continue");

  return (
    <section aria-label="Confidence timeline" className="card">
      <span className="caption">Confidence timeline</span>
      <div className="timeline-legend" aria-hidden="true">
        <span className="caption">
          <span className="swatch" style={{ background: "var(--chart-1)" }} />
          spaghetti score
        </span>
        <span className="caption">
          <span className="swatch" style={{ background: "var(--chart-3)" }} />
          confidence
        </span>
        <span className="caption">
          <span className="swatch" style={{ background: "var(--chart-2)" }} />
          pause threshold
        </span>
        {hasDegraded ? (
          <span className="caption">
            <span className="swatch" style={{ background: "var(--degraded)" }} />
            degraded
          </span>
        ) : null}
      </div>
      {/* DP-UI-V2 §5.1: the threshold is DRAWN AND LABELLED with its number. A
          curve crossing an unlabelled line proves nothing to a judge watching a
          video, and SVG text inside a preserveAspectRatio="none" viewBox is
          distorted, so the label is HTML. */}
      <div className="timeline-readouts">
        <span className="readout" data-role="threshold">
          Pause threshold {pauseThreshold.toFixed(2)}
        </span>
        <span className="readout" data-role="peak">
          Peak {peak.toFixed(2)}
        </span>
        <span className="small muted" data-role="events">
          {alerts.length === 0
            ? "no escalation yet"
            : `${alerts.length} escalations, first at frame ${alerts[0]!.frame_index} — ${alerts[0]!.action.replace(/_/g, " ")}`}
        </span>
      </div>
      {model === null ? (
        <p className="timeline-empty" role="status">
          Waiting for the first measurements…
        </p>
      ) : (
        <svg
          data-demo-focus="timeline"
          viewBox={`0 0 ${W} ${H}`}
          preserveAspectRatio="none"
          style={{ width: "100%", height: H, display: "block" }}
          role="img"
          aria-label={`spaghetti score and confidence over ${scores.length} frames`}
        >
          <line
            x1={PAD}
            x2={W - PAD}
            y1={model.thresholdY}
            y2={model.thresholdY}
            stroke="var(--chart-2)"
            strokeWidth="3"
            strokeDasharray="10 6"
            className={peak >= pauseThreshold ? "timeline-threshold crossed" : "timeline-threshold"}
          />
          <path d={model.conf} fill="none" stroke="var(--chart-3)" strokeWidth="3" />
          <path
            d={model.spag}
            fill="none"
            stroke="var(--chart-1)"
            strokeWidth={peak >= pauseThreshold ? 5 : 4}
            className={peak >= pauseThreshold ? "timeline-curve above" : "timeline-curve"}
          />
          {model.degraded.map((p, i) => (
            <circle key={`g${i}`} cx={p.cx} cy={p.cy} r="6" fill="none" stroke="var(--degraded)" strokeWidth="3" />
          ))}
          {model.markers.map(({ d, cx, cy }) => {
            const title = `${d.action} — ${d.reason_code} @ frame ${d.frame_index}`;
            if (d.action === "request_pause_approval") {
              return (
                <circle key={title} cx={cx} cy={cy} r="9" fill="var(--chart-2)">
                  <title>{title}</title>
                </circle>
              );
            }
            if (d.action === "capture_evidence") {
              return (
                <rect key={title} x={cx - 7} y={cy - 7} width="14" height="14" fill="var(--chart-1)">
                  <title>{title}</title>
                </rect>
              );
            }
            const s = 10;
            return (
              <polygon
                key={title}
                points={`${cx},${cy - s} ${cx + s},${cy + s} ${cx - s},${cy + s}`}
                fill="var(--chart-1)"
              >
                <title>{title}</title>
              </polygon>
            );
          })}
        </svg>
      )}
    </section>
  );
}
