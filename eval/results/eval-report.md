# Evaluation — Spaghetti Sentinel

9/9 cases passed (1 skipped).

## Environment

| fact | value |
|---|---|
| backend | cool |
| opencv_version | 5.0.0 |
| cool_version | None |
| arch | AMD64 |
| rationale_source_observed | ['fallback'] |
| evidence_backend | local |
| synthetic_cases | 4 |
| real_cases | 0 |

## Results by axis

- task_effectiveness: 4/4 (score 1.00) — Task effectiveness 20%
- failure_handling: 3/3 (score 1.00) — Failure handling 15%
- observability: 4/4 (score 1.00) — Observability (within 15%)
- human_control: 1/1 (score 1.00) — Human control (within 15%)

## Cases

### nominal-no-pause — PASS

A clean print must never interrupt the operator.

expected: `{"pause_recommended": false, "max_action": "continue"}`

observed: `{"pause_recommended": false, "requires_human": false, "first_alert_frame": null, "detect_latency_frames": null, "detect_latency_s": null, "actions": {"continue": 100}, "approvals": 0, "approval_unanswered": false, "evidence_uris": 0, "trace_steps": 300, "degraded": false, "completes": true}`

### warning-captures-not-pauses — PASS

A cosmetic defect should be recorded, not escalated to a human.

expected: `{"pause_recommended": false, "min_action": "capture_evidence", "onset_frame": 120, "max_detect_latency_frames": 45}`

observed: `{"pause_recommended": false, "requires_human": false, "first_alert_frame": 147, "detect_latency_frames": 27, "detect_latency_s": 0.9, "actions": {"continue": 49, "nudge_parameters": 4, "capture_evidence": 47}, "approvals": 0, "approval_unanswered": false, "evidence_uris": 47, "trace_steps": 300, "degraded": false, "completes": true}`

### failure-pauses-and-asks — PASS

A real failure must reach a human, with evidence, quickly.

expected: `{"pause_recommended": true, "requires_human": true, "onset_frame": 150, "max_detect_latency_frames": 45}`

observed: `{"pause_recommended": true, "requires_human": true, "first_alert_frame": 168, "detect_latency_frames": 18, "detect_latency_s": 0.6, "actions": {"continue": 56, "nudge_parameters": 1, "capture_evidence": 8, "request_pause_approval": 35}, "approvals": 35, "approval_unanswered": false, "evidence_uris": 43, "trace_steps": 300, "degraded": false, "completes": true}`

### lighting-negative — PASS

A global lighting change must not be mistaken for a failure.

expected: `{"pause_recommended": false, "max_action": "capture_evidence"}`

observed: `{"pause_recommended": false, "requires_human": false, "first_alert_frame": 102, "detect_latency_frames": null, "detect_latency_s": null, "actions": {"continue": 92, "capture_evidence": 8}, "approvals": 0, "approval_unanswered": false, "evidence_uris": 8, "trace_steps": 300, "degraded": false, "completes": true}`

### degraded-frames-never-escalate — PASS

When the vision pipeline cannot measure, the system must fall silent, not guess.

expected: `{"pause_recommended": false, "completes": true}`

observed: `{"pause_recommended": false, "requires_human": false, "first_alert_frame": null, "detect_latency_frames": null, "detect_latency_s": null, "actions": {"continue": 100}, "approvals": 0, "approval_unanswered": false, "evidence_uris": 0, "trace_steps": 300, "degraded": true, "completes": true}`

### vision-source-dies-midrun — PASS

A crash in the analysis must not take the run down.

expected: `{"completes": true, "degraded": true}`

observed: `{"pause_recommended": true, "requires_human": true, "first_alert_frame": 168, "detect_latency_frames": null, "detect_latency_s": null, "actions": {"continue": 55, "nudge_parameters": 1, "capture_evidence": 8, "request_pause_approval": 35}, "approvals": 35, "approval_unanswered": false, "evidence_uris": 43, "trace_steps": 298, "degraded": true, "completes": true}`

### evidence-store-unavailable — PASS

Losing the evidence vault must not lose the alert.

expected: `{"completes": true, "pause_recommended": true, "evidence_uris": 0}`

observed: `{"pause_recommended": true, "requires_human": true, "first_alert_frame": 168, "detect_latency_frames": null, "detect_latency_s": null, "actions": {"continue": 56, "nudge_parameters": 1, "capture_evidence": 8, "request_pause_approval": 35}, "approvals": 35, "approval_unanswered": false, "evidence_uris": 0, "trace_steps": 300, "degraded": false, "completes": true}`

### nobody-answers-the-prompt — PASS

An unanswered human prompt must be recorded as unanswered, and the run must end cleanly.

expected: `{"completes": true, "approval_unanswered": true}`

observed: `{"pause_recommended": true, "requires_human": true, "first_alert_frame": 168, "detect_latency_frames": null, "detect_latency_s": null, "actions": {"continue": 56, "nudge_parameters": 1, "capture_evidence": 8, "request_pause_approval": 35}, "approvals": 35, "approval_unanswered": true, "evidence_uris": 43, "trace_steps": 300, "degraded": false, "completes": true}`

### threshold-flip-changes-action — PASS

The qualifying property: vision output changes what the system does next.

expected: `{"action_changes_at_threshold": true}`

observed: `{"action_changes_at_threshold": true, "action_below": "capture_evidence", "action_above": "request_pause_approval", "delta_in_score": 0.02}`

### real-footage — SKIPPED

Does any of this survive contact with non-synthetic footage?

expected: `{"completes": true}`

observed: `{}`

failure: no real footage present

## Failure cases and limitations

Every case passed; the known limitations below still apply.
- Three of the four labelled clips are synthetic and were generated by this repository; they exercise the pipeline's discrimination, not real-world lighting, camera noise or printer variety.
- The scoring weights in app/vision/pipeline.py are fixed constants chosen by inspection, not learned from a labelled dataset; they are a heuristic, not a trained model.
- Detection latency is measured in sampled frames at sample_every_n=3, so the reported latency is granular to 3 source frames (0.1 s at 30 fps).
- The system recommends a pause; it never actuates one. Any claim of saved filament is modelled from the detection frame, not measured on a printer.
- Confidence is a deterministic penalty product, not a calibrated probability; it should not be read as 'this many percent of such alerts are real'.
- No adversarial or occlusion cases are evaluated (a hand entering frame, the camera moving mid-print beyond the stabiliser's ±24 px clamp).

## How to reproduce

```bash
S3_BUCKET= python eval/run_eval.py --out eval/results
```
Commit: `56857b1`
