import type { JSX } from "react";

export type ConnectionPillProps = {
  status: "connecting" | "open" | "closed" | "error";
  onReconnect: () => void;
};

const LABEL: Record<ConnectionPillProps["status"], string> = {
  connecting: "connecting",
  open: "live",
  closed: "snapshot",
  error: "stream error",
};

export function ConnectionPill({ status, onReconnect }: ConnectionPillProps): JSX.Element {
  const cls =
    status === "open" ? "pill pill-live"
    : status === "error" ? "pill pill-bad"
    : status === "connecting" ? "pill pill-connecting"
    : "pill pill-idle";
  return (
    <span className={cls} role="status" aria-label={`stream status: ${LABEL[status]}`}>
      <span className="dot" aria-hidden="true" />
      {LABEL[status]}
      {status === "closed" ? (
        <span className="small muted">&nbsp;snapshot mode — showing the completed run</span>
      ) : null}
      {status === "error" ? (
        <button type="button" className="btn btn-outline" onClick={onReconnect}>
          Reconnect
        </button>
      ) : null}
    </span>
  );
}
