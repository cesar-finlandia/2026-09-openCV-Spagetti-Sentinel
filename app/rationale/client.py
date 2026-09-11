"""explain() — the ONLY outbound LLM call in this application (REQ-F09)."""
from __future__ import annotations

import asyncio
import json
import logging
import os

from app.contracts.types import AgentDecision, RationaleResult, RunConfig, VisionScores
from app.rationale.history import MAX_PROMPT_TOKENS, build_history, estimate_tokens
from app.rationale.prompts import SYSTEM_PROMPT, parse_response, render_user

logger = logging.getLogger("rationale.client")

BEDROCK_TIMEOUT_MS: int = 6000
"""Short on purpose: the rationale is decorative, and the run must not stall on it."""

FALLBACK_CHECKLISTS: dict[str, list[str]] = {
    "nominal": [
        "No action needed — keep watching.",
    ],
    "low_confidence": [
        "Check the camera view is unobstructed and the bed is lit evenly.",
        "Re-run once the print has advanced past the first few layers.",
    ],
    "texture_rising": [
        "Look at the saved clip before touching the printer.",
        "Check whether the part has detached from the bed at a corner.",
        "Confirm the nozzle is not dragging through a raised region.",
    ],
    "first_layer_shift": [
        "Compare the current bed coverage with the first layer in the saved frame.",
        "Check bed adhesion at the corners and the Z-offset.",
        "If the first layer has lifted, stopping now saves the remaining filament.",
    ],
    "spaghetti_confirmed": [
        "Open the saved clip and confirm loose filament is accumulating.",
        "If confirmed, approve the pause — the print will not recover on its own.",
        "Clear the nozzle before restarting; extruded filament tends to weld to it.",
        "Note the layer height and bed temperature for the retry.",
    ],
    "default": [
        "Open the saved clip and the saved frame.",
        "Decide whether to continue, based on what the footage shows.",
    ],
}


def _fallback_text(decision: AgentDecision, scores: VisionScores) -> str:
    fi = decision.get("frame_index", scores.get("frame_index", 0))
    t_s = f"{scores.get('t_ms', 0) / 1000.0:.1f}"
    return (
        f"Frame {fi} at {t_s} seconds scored {scores.get('spaghetti_score', 0.0):.2f} "
        f"for spaghetti risk with {scores.get('confidence', 0.0):.2f} confidence, "
        f"against a threshold of {decision.get('threshold', 0.0):.2f}. "
        f"Edge regularity was {scores.get('edge_regularity', 0.0):.2f} and texture disorder "
        f"{scores.get('texture_disorder', 0.0):.2f}. The system selected "
        f"\"{decision.get('action')}\" ({decision.get('reason_code')}). "
        f"This explanation was generated from the measurements themselves; "
        f"the language model was not available for this frame."
    )


def _fallback(decision: AgentDecision, scores: VisionScores) -> RationaleResult:
    rc = decision.get("reason_code", "default")
    return {
        "text": _fallback_text(decision, scores),
        "checklist": list(FALLBACK_CHECKLISTS.get(rc, FALLBACK_CHECKLISTS["default"])),
        "source": "fallback",
        "degraded": True,
    }


def budget_exhausted(cfg: RunConfig) -> bool:
    """True when metered spend for this process has reached settings.llm_budget_usd."""
    try:
        from app.config.settings import load_settings
        from src.cost.store import get_default_store

        settings = load_settings()
        limit = settings.llm_budget_usd
        if limit <= 0:
            return False
        store = get_default_store()
        totals = store.totals_by_provider()
        bed = totals.get("bedrock")
        if not bed:
            return False
        acc = bed.get("estimated_cost_usd") or 0.0
        try:
            return float(acc) >= float(limit)
        except Exception:
            return False
    except Exception:
        return False


def _invoke(user: str) -> str:
    import boto3

    from app.config.settings import load_settings

    settings = load_settings()
    client = boto3.client("bedrock-runtime", region_name=settings.aws_region)
    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 400,
        "temperature": 0.2,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": [{"type": "text", "text": user}]}],
    })
    resp = client.invoke_model(modelId=settings.bedrock_model_id, body=body,
                               contentType="application/json", accept="application/json")
    payload = json.loads(resp["body"].read())
    return "".join(b.get("text", "") for b in payload.get("content", []))


try:
    from src.cost.meter import with_cost_guardrail
    from src.resilience import is_degraded_result, with_resilience

    _metered = with_cost_guardrail(_invoke, {"provider": "bedrock", "tag": "rationale"})
    _guarded = with_resilience(_metered, {"timeout_ms": BEDROCK_TIMEOUT_MS, "retries": 1,
                                          "fallback_chain": {"order": ["cache", "none"]}})
except Exception:  # pragma: no cover
    def _guarded(text: str):  # type: ignore
        return _invoke(text)

    def is_degraded_result(v):  # type: ignore
        return isinstance(v, dict) and v.get("degraded") is True


async def explain(decision: AgentDecision, scores: VisionScores,
                  history: list[VisionScores], cfg: RunConfig) -> RationaleResult:
    """Produce {text, checklist, source, degraded} for an ALREADY-MADE decision."""
    try:
        from app.config.settings import load_settings

        settings = load_settings()
        # Replay short-circuit.
        try:
            if cfg.get("replay"):
                from src.resilience import create_golden_cache

                from app.fixtures.seed_cache import rationale_key

                src = cfg.get("source", "")
                fid = os.path.splitext(os.path.basename(src))[0]
                hit = create_golden_cache(settings.cache_dir).get(
                    rationale_key(fid, decision.get("frame_index", 0)))
                if isinstance(hit, dict) and hit.get("text"):
                    return {"text": str(hit["text"])[:600],
                            "checklist": list(hit.get("checklist", []))[:6],
                            "source": "fallback", "degraded": False}
        except Exception:
            pass
        # Budget gate.
        try:
            if budget_exhausted(cfg):
                logger.info("rationale: LLM budget reached, using deterministic rationale")
                return _fallback(decision, scores)
        except Exception:
            pass
        hist = build_history(history or [scores])
        user = render_user(decision, scores, hist)
        # Token ceiling.
        try:
            guard = 0
            while estimate_tokens(SYSTEM_PROMPT + user) > MAX_PROMPT_TOKENS and len(hist) > 1 and guard < 50:
                del hist[1]
                user = render_user(decision, scores, hist)
                guard += 1
            if estimate_tokens(SYSTEM_PROMPT + user) > MAX_PROMPT_TOKENS and len(hist) <= 1:
                user = user[-(MAX_PROMPT_TOKENS * 4):]
        except Exception:
            pass
        try:
            raw = await asyncio.to_thread(_guarded, user)
        except Exception as err:
            logger.warning("rationale: model unavailable (%s); using deterministic rationale",
                           type(err).__name__)
            return _fallback(decision, scores)
        try:
            if is_degraded_result(raw) or not isinstance(raw, str) or not raw.strip():
                reason = raw.get("reason", "empty") if isinstance(raw, dict) else "empty"
                logger.warning("rationale: model unavailable (%s); using deterministic rationale", reason)
                return _fallback(decision, scores)
        except Exception:
            return _fallback(decision, scores)
        text, checklist = parse_response(raw)
        if not text:
            return _fallback(decision, scores)
        return {"text": text,
                "checklist": checklist or list(FALLBACK_CHECKLISTS.get(
                    decision.get("reason_code", "default"), FALLBACK_CHECKLISTS["default"])),
                "source": "bedrock", "degraded": False}
    except Exception as err:
        logger.warning("rationale: explain failed (%s); using deterministic rationale",
                       type(err).__name__)
        try:
            return _fallback(decision, scores)
        except Exception:
            return {"text": "Measurement-based rationale unavailable.", "checklist": [],
                    "source": "fallback", "degraded": True}
