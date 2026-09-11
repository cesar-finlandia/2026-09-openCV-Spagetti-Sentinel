"""Shared types for Spaghetti Sentinel — the SINGLE definition of every cross-module shape.

No other module in this repository may declare VisionScores, AgentDecision, RunConfig,
RunSummary, TraceStep, RationaleResult, ApprovalRecord, BackendInfo or FrameRef.
Consumers import them from here. Frozen by master_blueprint_entry.md §2.5.
"""
from __future__ import annotations

from typing import Any, Literal, TypedDict

BackendName = Literal["cool", "baseline"]
ActionName = Literal["continue", "nudge_parameters", "capture_evidence", "request_pause_approval"]
RationaleSource = Literal["bedrock", "fallback"]
TraceKind = Literal["perception", "decision", "action", "tool_call"]


class BackendInfo(TypedDict):
    name: BackendName
    opencv_version: str
    cool_version: str | None
    arch: str
    cool_available: bool


class FrameRef(TypedDict):
    index: int
    t_ms: int
    path: str | None


class VisionScores(TypedDict):
    frame_index: int
    t_ms: int
    first_layer_coverage: float
    edge_regularity: float
    motion_energy: float
    texture_disorder: float
    spaghetti_score: float
    confidence: float
    roi: list[int]
    backend: BackendName
    ops_ms: dict[str, float]
    degraded: bool


class AgentDecision(TypedDict):
    frame_index: int
    t_ms: int
    action: ActionName
    reason_code: str
    spaghetti_score: float
    confidence: float
    threshold: float
    requires_human: bool
    rationale: str
    checklist: list[str]
    evidence_uri: str | None
    rationale_source: RationaleSource
    degraded: bool


class RationaleResult(TypedDict):
    text: str
    checklist: list[str]
    source: RationaleSource
    degraded: bool


class ApprovalRecord(TypedDict):
    approval_id: str
    run_id: str
    frame_index: int
    approved: bool | None
    created_at: str
    resolved_at: str | None


class TraceStep(TypedDict):
    sequence: int
    kind: TraceKind
    step_id: str
    t_ms: int
    tool: str | None
    input: dict[str, Any]
    output: dict[str, Any]


class RunConfig(TypedDict):
    run_id: str
    source: str
    backend: BackendName
    sample_every_n: int
    max_frames: int
    roi: list[int] | None
    thresholds: dict[str, float]
    synthetic: bool
    replay: bool
    evidence_prefix: str


class RunSummary(TypedDict):
    run_id: str
    backend: BackendName
    frames_processed: int
    frames_sampled: int
    wall_ms: int
    fps: float
    p50_frame_ms: float
    p95_frame_ms: float
    decisions: list[AgentDecision]
    first_alert_frame: int | None
    first_alert_t_ms: int | None
    pause_recommended: bool
    approvals: list[ApprovalRecord]
    evidence_uris: list[str]
    degraded: bool
    synthetic: bool
    build_marker: str
