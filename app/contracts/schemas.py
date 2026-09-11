"""JSON Schemas for the three validated shapes, loaded once from disk.

Used with src.resilience.validate(value, schema) -> list[ValidationError].
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent


def _load(name: str) -> dict[str, Any]:
    return json.loads((_HERE / name).read_text(encoding="utf-8"))


VISION_SCORES_SCHEMA: dict[str, Any] = _load("vision-scores.schema.json")
AGENT_DECISION_SCHEMA: dict[str, Any] = _load("agent-decision.schema.json")
RUN_SUMMARY_SCHEMA: dict[str, Any] = _load("run-summary.schema.json")
