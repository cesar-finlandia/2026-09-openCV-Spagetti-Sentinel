import type { EventEnvelope } from "src/platform/transport";
import { StreamingTextRenderer } from "src/platform/ui";
import type { AgentDecision } from "../selectors";

export type DecisionCardProps = { decision: AgentDecision | null; envelopes: EventEnvelope[] };

export function DecisionCard(props: DecisionCardProps) {
  const { decision, envelopes } = props;
  if (!decision) {
    return (
      <div className="ss-card ss-muted">No decision yet — start a run to see the agent act.</div>
    );
  }
  return (
    <div className="ss-card">
      <div className="ss-row">
        <strong>{decision.action}</strong>
        <span className="ss-chip">{decision.reason_code}</span>
        <span className="ss-muted">
          frame {decision.frame_index} · {(decision.t_ms / 1000).toFixed(1)}s · score{" "}
          {decision.spaghetti_score.toFixed(2)} / {decision.threshold.toFixed(2)} · conf{" "}
          {decision.confidence.toFixed(2)}
        </span>
        <span className="ss-chip">
          source: {decision.rationale_source === "bedrock" ? "bedrock" : "measured fallback"}
        </span>
      </div>
      <StreamingTextRenderer envelopes={envelopes} stepId="rationale" />
      {decision.checklist.length ? (
        <ul>
          {decision.checklist.map((c, i) => (
            <li key={i}>{c}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
