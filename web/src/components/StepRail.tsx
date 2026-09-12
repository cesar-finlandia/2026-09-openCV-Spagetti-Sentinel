import type { JSX } from "react";
import type { EventEnvelope } from "src/platform/transport";
import { StepStatusIndicator } from "src/platform/ui";
import { STEP_LABELS } from "../selectors";

export type StepRailProps = {
  envelopes: EventEnvelope[];
  orientation: "vertical" | "horizontal";
};

export function StepRail({ envelopes, orientation }: StepRailProps): JSX.Element {
  return (
    <section aria-label="Pipeline progress" className="card">
      <span className="caption">Pipeline</span>
      <div className="step-rail" data-orientation={orientation}>
        <StepStatusIndicator envelopes={envelopes} labelMap={STEP_LABELS} title="" />
      </div>
    </section>
  );
}
