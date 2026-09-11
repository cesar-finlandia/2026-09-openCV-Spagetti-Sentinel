"""Public surface of the agent module."""
from app.agent.loop import (
    APPROVAL_TIMEOUT_S,
    EVIDENCE_WINDOW,
    ApproverFn,
    EmitFn,
    run_agent,
)
from app.agent.policy import COVERAGE_DROP_THRESHOLD, REASON_CODES, SUSTAIN_FRAMES, decide
from app.agent.tools import TOOLS, ToolError, ToolSpec, call_tool, tool_manifest
from app.agent.trace import TraceRecorder

__all__ = [
    "TOOLS", "ToolSpec", "ToolError", "call_tool", "tool_manifest",
    "decide", "REASON_CODES", "SUSTAIN_FRAMES", "COVERAGE_DROP_THRESHOLD",
    "TraceRecorder",
    "run_agent", "EmitFn", "ApproverFn", "EVIDENCE_WINDOW", "APPROVAL_TIMEOUT_S",
]
