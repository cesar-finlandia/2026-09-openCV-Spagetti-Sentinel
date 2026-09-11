"""Settings — the ONLY module in app/ that reads os.environ.

Every other module receives a Settings object or a RunConfig. Secrets are read here and
never logged, never placed in an EventEnvelope payload, never written to disk (REQ-N07).
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True)
class Settings:
    backend: str                      # SS_BACKEND: "cool" | "baseline"; default "cool"
    replay: bool                      # SS_REPLAY=1 -> offline replay mode (REQ-F17)
    aws_region: str                   # AWS_REGION; default "us-east-1"
    s3_bucket: str | None             # S3_BUCKET; None -> local evidence fallback
    bedrock_model_id: str             # BEDROCK_MODEL_ID; default in DEFAULTS
    evidence_dir: str                 # SS_EVIDENCE_DIR; local fallback root
    cache_dir: str                    # SS_CACHE_DIR; golden cache root
    fixtures_dir: str                 # SS_FIXTURES_DIR; default "fixtures"
    max_frames: int                   # SS_MAX_FRAMES; default 900
    sample_every_n: int               # SS_SAMPLE_EVERY_N; default 3
    thresholds: dict[str, float] = field(default_factory=dict)  # warn/pause/confidence_floor
    llm_budget_usd: float = 5.0       # SS_LLM_BUDGET_USD
    build_marker: str = "dev"         # BUILD_MARKER


DEFAULTS: dict[str, str] = {
    "SS_BACKEND": "cool",
    "SS_REPLAY": "0",
    "AWS_REGION": "us-east-1",
    "BEDROCK_MODEL_ID": "anthropic.claude-3-5-haiku-20241022-v1:0",
    "SS_EVIDENCE_DIR": ".evidence",
    "SS_CACHE_DIR": ".golden-cache",
    "SS_FIXTURES_DIR": "fixtures",
    "SS_MAX_FRAMES": "900",
    "SS_SAMPLE_EVERY_N": "3",
    "SS_WARN_THRESHOLD": "0.45",
    "SS_PAUSE_THRESHOLD": "0.72",
    "SS_CONFIDENCE_FLOOR": "0.55",
    "SS_LLM_BUDGET_USD": "5.0",
    "BUILD_MARKER": "dev",
}


def _warn(key: str, raw: str, default: str) -> None:
    print(f"settings: {key} invalid ({raw}), using default {default}", file=sys.stderr)


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Build a Settings from `env` (default: os.environ), substituting DEFAULTS.

    Never raises: a malformed numeric value warns to stderr and uses its default.
    """
    source: Mapping[str, str] = env if env is not None else os.environ

    def get(key: str) -> str:
        v = source.get(key)
        if v is None or (isinstance(v, str) and v == ""):
            return DEFAULTS[key]
        return v

    def get_int(key: str) -> int:
        raw = get(key)
        try:
            return int(raw)
        except (ValueError, TypeError):
            _warn(key, str(raw), DEFAULTS[key])
            return int(DEFAULTS[key])

    def get_float(key: str) -> float:
        raw = get(key)
        try:
            return float(raw)
        except (ValueError, TypeError):
            _warn(key, str(raw), DEFAULTS[key])
            return float(DEFAULTS[key])

    backend = get("SS_BACKEND").strip().lower()
    if backend not in ("cool", "baseline"):
        print(f"settings: SS_BACKEND invalid ({backend}), using default cool", file=sys.stderr)
        backend = "cool"
    replay = get("SS_REPLAY").strip() == "1"
    aws_region = get("AWS_REGION")
    _s3 = source.get("S3_BUCKET")
    s3_bucket = _s3 if _s3 else None
    bedrock_model_id = get("BEDROCK_MODEL_ID")
    evidence_dir = get("SS_EVIDENCE_DIR")
    cache_dir = get("SS_CACHE_DIR")
    fixtures_dir = get("SS_FIXTURES_DIR")
    max_frames = get_int("SS_MAX_FRAMES")
    sample_every_n = get_int("SS_SAMPLE_EVERY_N")
    llm_budget_usd = get_float("SS_LLM_BUDGET_USD")
    build_marker = get("BUILD_MARKER")

    def clamp01(x: float) -> float:
        return min(1.0, max(0.0, float(x)))

    thresholds = {
        "warn": clamp01(get_float("SS_WARN_THRESHOLD")),
        "pause": clamp01(get_float("SS_PAUSE_THRESHOLD")),
        "confidence_floor": clamp01(get_float("SS_CONFIDENCE_FLOOR")),
    }
    if thresholds["warn"] >= thresholds["pause"]:
        print(
            "settings: warn threshold must be below pause threshold, using defaults 0.45/0.72",
            file=sys.stderr,
        )
        thresholds["warn"] = 0.45
        thresholds["pause"] = 0.72

    return Settings(
        backend=backend,
        replay=replay,
        aws_region=aws_region,
        s3_bucket=s3_bucket,
        bedrock_model_id=bedrock_model_id,
        evidence_dir=evidence_dir,
        cache_dir=cache_dir,
        fixtures_dir=fixtures_dir,
        max_frames=max_frames,
        sample_every_n=sample_every_n,
        thresholds=thresholds,
        llm_budget_usd=llm_budget_usd,
        build_marker=build_marker,
    )
