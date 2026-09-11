"""EnvelopePublisher — the ONLY builder of EventEnvelope values in this application."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from app.contracts.steps import ALL_STEPS

logger = logging.getLogger("api.publisher")

MAX_COLLECTED: int = 4000


def _load_envelope_schema() -> dict[str, Any]:
    for path in ("contracts/event-envelope.schema.json",
                 "contracts/event-envelope.schema.json".replace("/", "\\")):
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            continue
    # Minimal fallback mirroring the chassis contract.
    return {
        "type": "object",
        "required": ["step_id", "status", "payload", "timestamp", "sequence"],
        "properties": {
            "step_id": {"type": "string"},
            "status": {"enum": ["started", "streaming", "done", "error"]},
            "payload": {"type": "object"},
            "timestamp": {"type": "string"},
            "sequence": {"type": "integer"},
        },
    }


ENVELOPE_SCHEMA: dict[str, Any] = _load_envelope_schema()

_PUBLISHERS: dict[str, "EnvelopePublisher"] = {}
_LAST: str | None = None


def _validate_envelope(envelope: dict) -> list:
    try:
        from src.resilience import validate

        res = validate(ENVELOPE_SCHEMA, envelope)
        if isinstance(res, dict):
            return res.get("errors", [])
        return list(res or [])
    except Exception:
        # Structural fallback: required keys + status enum + step pattern.
        try:
            for k in ("step_id", "status", "payload", "timestamp", "sequence"):
                if k not in envelope:
                    return [{"path": f"/{k}", "message": "missing", "code": "required"}]
            if envelope["status"] not in ("started", "streaming", "done", "error"):
                return [{"path": "/status", "message": "bad status", "code": "enum"}]
            return []
        except Exception:
            return [{"path": "/", "message": "invalid", "code": "type"}]


class EnvelopePublisher:
    trace_id: str
    sequence: int

    def __init__(self, trace_id: str) -> None:
        self.trace_id = trace_id
        self.sequence = 0
        self._collected: list[dict[str, Any]] = []
        self._degraded = False
        self._closed = False

    async def publish(self, step_id: str, status: str,
                      payload: dict[str, Any] | None = None,
                      degraded: bool = False) -> None:
        """Build, validate and emit one EventEnvelope. Never raises."""
        try:
            if self._closed:
                return
            if step_id not in ALL_STEPS:
                logger.error("api: refusing unknown step_id %s", step_id)
                return
            envelope = {
                "step_id": step_id, "status": status, "payload": payload or {},
                "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "sequence": self.sequence, "trace_id": self.trace_id,
                "degraded": bool(degraded),
            }
            errors = _validate_envelope(envelope)
            if errors:
                logger.error("api: envelope validation failed (%s)", errors[0])
                return
            self.sequence += 1
            self._collected.append(envelope)
            if len(self._collected) > MAX_COLLECTED:
                del self._collected[:len(self._collected) - MAX_COLLECTED]
            if degraded:
                self._degraded = True
            try:
                from src.platform.transport.stream_router import HUB

                await HUB.publish(envelope)
            except Exception as err:
                logger.warning("api: hub publish failed (%s)", type(err).__name__)
        except Exception as err:
            logger.error("api: publish failed (%s)", type(err).__name__)

    def collect(self) -> dict[str, Any]:
        """{"trace_id": …, "events": [EventEnvelope, …], "degraded": bool}."""
        return {"trace_id": self.trace_id, "events": list(self._collected),
                "degraded": self._degraded}

    async def close(self) -> None:
        """Mark this trace complete. No further envelopes are accepted."""
        self._closed = True


def create_publisher(trace_id: str) -> EnvelopePublisher:
    """Factory. Registers the publisher in the process registry."""
    global _LAST
    pub = EnvelopePublisher(trace_id)
    _PUBLISHERS[trace_id] = pub
    _LAST = trace_id
    return pub


def get_publisher(trace_id: str | None = None) -> EnvelopePublisher | None:
    """Look up a publisher by trace id; `None` returns the most recently created one."""
    if trace_id is not None:
        return _PUBLISHERS.get(trace_id)
    if _LAST is None:
        return None
    return _PUBLISHERS.get(_LAST)
