"""DP-AGENT tool registry tests."""
from __future__ import annotations


def test_registry_shape_and_rejection():
    from app.agent.tools import TOOLS, ToolError, call_tool, tool_manifest

    m = tool_manifest()
    try:
        call_tool("score_frame", {"frame_index": "x", "t_ms": 0})
        bad = "NO"
    except ToolError:
        bad = "rejected"
    try:
        call_tool("nope", {})
        unk = "NO"
    except ToolError:
        unk = "rejected"
    assert len(TOOLS) == 4
    assert sorted(TOOLS) == ["capture_evidence", "detect_roi", "probe_source", "score_frame"]
    assert all("fn" not in t for t in m)
    assert bad == "rejected" and unk == "rejected"
