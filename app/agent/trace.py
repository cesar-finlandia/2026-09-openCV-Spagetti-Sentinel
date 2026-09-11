"""TraceRecorder — the artefact the Agentic Vision addendum quotes."""
from __future__ import annotations

import json
import logging
import os

from app.contracts.types import TraceStep

logger = logging.getLogger("agent.trace")


class TraceRecorder:
    run_id: str

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self._steps: list[TraceStep] = []
        self._seq = 0

    def record(self, kind: str, step_id: str, t_ms: int, input: dict, output: dict,
               tool: str | None = None) -> TraceStep:
        """Append one step with the next sequence number and return it. Never raises."""
        try:
            step: TraceStep = {
                "sequence": self._seq, "kind": kind, "step_id": step_id,
                "t_ms": int(t_ms), "tool": tool,
                "input": dict(input or {}), "output": dict(output or {}),
            }
            self._steps.append(step)
            self._seq += 1
            return step
        except Exception as err:
            logger.warning("trace: record failed (%s)", type(err).__name__)
            return {"sequence": -1, "kind": "action", "step_id": step_id,
                    "t_ms": 0, "tool": tool, "input": {}, "output": {}}

    def steps(self) -> list[TraceStep]:
        """The recorded steps, in order. The returned list is a copy."""
        return list(self._steps)

    def write(self, path: str) -> str:
        """Write the trace as JSON Lines to `path`, creating parent dirs. Returns `path`."""
        try:
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                for st in self._steps:
                    fh.write(json.dumps(st, default=str) + "\n")
            return path
        except Exception as err:
            logger.warning("trace: write failed (%s)", type(err).__name__)
            return ""

    def summary(self) -> dict:
        """{steps: int, tool_calls: int, decisions: int, actions: int, by_tool: {name: count}}."""
        try:
            by_tool: dict[str, int] = {}
            tc = dec = act = 0
            for st in self._steps:
                if st.get("kind") == "tool_call":
                    tc += 1
                    t = st.get("tool") or "?"
                    by_tool[t] = by_tool.get(t, 0) + 1
                elif st.get("kind") == "decision":
                    dec += 1
                elif st.get("kind") == "action":
                    act += 1
            return {"steps": len(self._steps), "tool_calls": tc, "decisions": dec,
                    "actions": act, "by_tool": by_tool}
        except Exception:
            return {"steps": 0, "tool_calls": 0, "decisions": 0, "actions": 0, "by_tool": {}}
