"""The ONLY permitted EventEnvelope step_id values (master_blueprint_entry.md §2.2).

Producers import these constants; they never write a step-id string literal.
app/contracts/steps.json mirrors ALL_STEPS for the TypeScript UI.
"""
from __future__ import annotations

STEP_RUN_START = "run-start"
STEP_INGEST = "ingest"
STEP_PERCEIVE = "perceive"
STEP_DECIDE = "decide"
STEP_ACT = "act"
STEP_AWAIT_APPROVAL = "await-approval"
STEP_APPROVAL_RESOLVED = "approval-resolved"
STEP_EVIDENCE_STORED = "evidence-stored"
STEP_RATIONALE = "rationale"
STEP_RUN_SUMMARY = "run-summary"

ALL_STEPS: tuple[str, ...] = (
    STEP_RUN_START,
    STEP_INGEST,
    STEP_PERCEIVE,
    STEP_DECIDE,
    STEP_ACT,
    STEP_AWAIT_APPROVAL,
    STEP_APPROVAL_RESOLVED,
    STEP_EVIDENCE_STORED,
    STEP_RATIONALE,
    STEP_RUN_SUMMARY,
)
