import type { JSX } from "react";
import type { EventEnvelope } from "src/platform/transport";
import { StreamingTextRenderer } from "src/platform/ui";
import type { AgentDecision } from "../selectors";

export type DecisionCardProps = {
  decision: AgentDecision | null;
  envelopes: EventEnvelope[];
};

export function DecisionCard({ decision, envelopes }: DecisionCardProps): JSX.Element {
  return (
    <section aria-label="Latest decision" className="card" data-demo-focus="decision">
      <span className="caption">Latest decision</span>
      {decision === null ? (
        <p className="small muted" role="status">
          No decision yet — the agent reports here once the first frames are analysed.
        </p>
      ) : (
        <div
          key={`${decision.frame_index}:${decision.action}`}
          className="decision-card"
          style={
            decision.degraded
              ? { borderLeft: "3px solid var(--degraded)", paddingLeft: "var(--sp-3)" }
              : undefined
          }
        >
          <div style={{ display: "flex", gap: "var(--sp-2)", alignItems: "center", flexWrap: "wrap" }}>
            <span className={`pill action-pill-${decision.action}`}>{decision.action.replace(/_/g, " ")}</span>
            <span className="mono muted">{decision.reason_code}</span>
            <span className="caption muted">rationale: {decision.rationale_source === "bedrock" ? "bedrock" : "measured fallback"}</span>
          </div>
          <p className="readout">
            Frame {decision.frame_index} at {(decision.t_ms / 1000).toFixed(1)} s scored{" "}
            {decision.spaghetti_score.toFixed(2)} against a threshold of {decision.threshold.toFixed(2)}.
          </p>
          <StreamingTextRenderer envelopes={envelopes} stepId="rationale" />
          {decision.checklist.length > 0 ? (
            <ul>
              {decision.checklist.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
          ) : null}
        </div>
      )}
    </section>
  );
}
