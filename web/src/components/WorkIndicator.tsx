import type { JSX } from "react";
import type { ActivityLine } from "../selectors";

export type WorkIndicatorProps = {
  active: boolean;
  line: ActivityLine;
  elapsedS: number;
  stalledS: number | null;
};

export function WorkIndicator({ line, elapsedS, stalledS }: WorkIndicatorProps): JSX.Element {
  const stalled = stalledS !== null;
  return (
    <div
      className={stalled ? "work-indicator work-indicator--stalled" : "work-indicator"}
      role="status"
      aria-live="polite"
      aria-label={line.text}
    >
      <div className="work-indicator__track" aria-hidden="true">
        <div className="work-indicator__bar" />
      </div>
      <div className="work-indicator__row">
        <span className="small" data-testid="work-indicator-text">{line.text}{stalled ? ` — no update for ${stalledS}s` : ""}</span>
        <span className="readout">{elapsedS.toFixed(1)}s</span>
      </div>
    </div>
  );
}
