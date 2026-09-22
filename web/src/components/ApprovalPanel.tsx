import { useEffect, useRef, useState, type JSX } from "react";
import type { PendingApproval } from "../selectors";

export type ApprovalPanelProps = {
  pending: PendingApproval;
  onAnswer: (approved: boolean) => void;
  busy: boolean;
  error: string | null;
  remainingS: number;
};

export function ApprovalPanel({ pending, onAnswer, busy, error, remainingS }: ApprovalPanelProps): JSX.Element | null {
  const approveRef = useRef<HTMLButtonElement | null>(null);
  const [answered, setAnswered] = useState(false);
  useEffect(() => {
    approveRef.current?.focus();
  }, []);
  useEffect(() => {
    setAnswered(false);
  }, [pending?.approvalId, error]);
  if (pending === null) return null;
  const d = pending.decision;
  const disabled = busy || answered;
  return (
    <section
      role="alertdialog"
      aria-live="assertive"
      aria-label="A human decision is needed"
      className="approval"
      data-demo-focus="approval"
    >
      <h1 className="h1">A human decision is needed</h1>
      <p className="readout">
        Frame {d.frame_index} at {(d.t_ms / 1000).toFixed(1)} s scored {d.spaghetti_score.toFixed(2)}{" "}
        against a threshold of {d.threshold.toFixed(2)}.
      </p>
      <p>{d.rationale}</p>
      {d.checklist.length > 0 ? (
        <ul>
          {d.checklist.map((c) => (
            <li key={c}>{c}</li>
          ))}
        </ul>
      ) : null}
      <div className="btn-row">
        <button
          ref={approveRef}
          type="button"
          className="btn btn-warn"
          disabled={disabled}
          onClick={() => {
            setAnswered(true);
            onAnswer(true);
          }}
        >
          Approve pause
        </button>
        <button
          type="button"
          className="btn btn-outline"
          disabled={disabled}
          onClick={() => {
            setAnswered(true);
            onAnswer(false);
          }}
        >
          Keep printing
        </button>
      </div>
      {error ? (
        <p className="small" role="alert" style={{ color: "var(--danger)" }}>
          Your answer did not reach the server — {error}. Press the button again.
        </p>
      ) : null}
      <p className="small muted">
        No answer within {remainingS}s means the system keeps watching and records that nobody answered.
      </p>
    </section>
  );
}
