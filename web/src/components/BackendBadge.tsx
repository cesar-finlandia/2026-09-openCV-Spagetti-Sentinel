import type { JSX } from "react";
import type { Health } from "../api";
import type { RunHeader } from "../selectors";

export type BackendBadgeProps = { header: RunHeader; health: Health | null };

export function BackendBadge({ header, health }: BackendBadgeProps): JSX.Element {
  if (health === null) {
    return (
      <span className="pill pill-idle" aria-label="backend unknown">
        <span className="dot" aria-hidden="true" />
        backend: unknown
      </span>
    );
  }
  const cool = health.cool_version !== null && header !== null && header.coolVersion !== null;
  return (
    <span className="pill" aria-label={cool ? `COOL backend on ${health.arch}` : "baseline OpenCV backend"}>
      <span className="dot" aria-hidden="true" />
      {cool ? (
        <span className="chip chip-accent">COOL on {health.arch}</span>
      ) : (
        <span>baseline OpenCV {health.opencv_version}</span>
      )}
      <span className="chip mono">{health.build_marker}</span>
    </span>
  );
}
