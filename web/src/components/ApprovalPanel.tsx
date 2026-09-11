import { useEffect, useState } from "react";
import type { PendingApproval } from "../selectors";

export type ApprovalPanelProps = {
  pending: PendingApproval;
  onAnswer: (approved: boolean) => void;
  busy: boolean;
};

export const APPROVAL_TIMEOUT_S = 120;

export function ApprovalPanel(props: ApprovalPanelProps) {
  const { pending, onAnswer, busy } = props;
  const [left, setLeft] = useState(APPROVAL_TIMEOUT_S);
  useEffect(() => {
    if (!pending) return;
    setLeft(APPROVAL_TIMEOUT_S);
    const t = setInterval(() => setLeft((v) => Math.max(0, v - 1)), 1000);
    return () => clearInterval(t);
  }, [pending?.approvalId]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!pending) return null;
  const d = pending.decision;
  return (
    <div className="ss-approval" role="alertdialog" aria-live="assertive">
      <h2 data-beat="approval-heading">A human decision is needed</h2>
      <p>
        Frame {d.frame_index} at {(d.t_ms / 1000).toFixed(1)} s scored{" "}
        {d.spaghetti_score.toFixed(2)} against a threshold of {d.threshold.toFixed(2)}.
      </p>
      {d.rationale ? <p>{d.rationale}</p> : null}
      {d.checklist.length ? (
        <ul>
          {d.checklist.map((c, i) => (
            <li key={i}>{c}</li>
          ))}
        </ul>
      ) : null}
      <div className="ss-row">
        <button
          className="ss-btn ss-btn--primary"
          data-beat="approve-button"
          disabled={busy}
          onClick={() => onAnswer(true)}
        >
          Approve pause
        </button>
        <button className="ss-btn" disabled={busy} onClick={() => onAnswer(false)}>
          Keep printing
        </button>
      </div>
      <p className="ss-muted">
        {left}s left. No answer within {APPROVAL_TIMEOUT_S}s means the system keeps watching and
        records that nobody answered.
      </p>
    </div>
  );
}
