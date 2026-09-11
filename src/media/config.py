# Requirement IDs: MED-03, MED-REU-01, RES-03, RES-04, GOV-RES-02, XCUT-08
"""MediaConfig load/merge/validate — Python mirror of config.ts.

DP-C §6.1 (schema + resolution precedence), §7.2 (error contract), §7.3
(safe defaults on missing/malformed config).

Resolution precedence (lowest → highest):
    1. config/media.json checked-in defaults (per-modality slice)
    2. per-call MediaConfig overrides passed to the loader/wrapper
    3. MED_* env overrides (operator swap mid-event, zero code change)

credentials_env holds ONLY the env var NAME; the value is read at call time via
resolve_credential(). A missing credential raises MediaError(
"missing_credentials") at CALL time — never at startup (GOV-RES-02).

Malformed/missing media config never crashes startup: invalid merges are warned
about and replaced by safe defaults {provider:"synthetic-fixture",
timeout_ms:15000, ocr_provider:"none"} (DP-C §7.3).

Domain-free (GOV-REU-02); imports only stdlib + src.resilience (RES-REU-01).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from src.resilience.validate import validate

_logger = logging.getLogger("media.config")

ModalityKey = str  # one of "stt" | "vision" | "pdf" | "tts"
MODALITIES = ("stt", "vision", "pdf", "tts")

MediaConfig = Dict[str, Any]  # partial slice; keys mirror contracts/media-config.schema.json
ResolvedMediaConfig = Dict[str, Any]  # fully-filled result of load_media_config


class MediaError(Exception):
    """Provider-side failure (DP-C §7.2). Raised so RES-01 can retry/fallback.

    Codes used across the media wrappers: provider_error | unknown_provider |
    missing_credentials. Bad-input errors are NOT raised — wrappers return them
    as UnifiedMediaMessage["error"] per DP-C §7.2.
    """

    def __init__(self, code: str, message: Optional[str] = None) -> None:
        super().__init__(message or code)
        self.code = code


# region Safe defaults + file access (DP-C §7.3, GOV-RES-02)

def _media_safe_defaults() -> ResolvedMediaConfig:
    """Fresh copy of the hardcoded safe defaults (always works offline)."""
    return {
        "provider": "synthetic-fixture",
        "secondary_provider": None,
        "timeout_ms": 15000,
        "retries": 1,
        "model": None,
        "prompt": None,
        "ocr_provider": "none",  # conservative: disable OCR when config is untrusted
        "credentials_env": "",
    }


_REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = _REPO_ROOT / "contracts" / "media-config.schema.json"
DEFAULTS_PATH = _REPO_ROOT / "config" / "media.json"

_schema_cache: Optional[Dict[str, Any]] = None


def _schema() -> Dict[str, Any]:
    global _schema_cache
    if _schema_cache is None:
        with open(SCHEMA_PATH, encoding="utf-8") as fh:
            _schema_cache = json.load(fh)
    return _schema_cache


_defaults_cache: Optional[Dict[str, MediaConfig]] = None


def _load_defaults_file() -> Dict[str, MediaConfig]:
    """Read + cache config/media.json. Missing/corrupt → {} with a warn
    (GOV-RES-02): never crashes startup; callers fall to safe defaults."""
    global _defaults_cache
    if _defaults_cache is not None:
        return _defaults_cache
    try:
        with open(DEFAULTS_PATH, encoding="utf-8") as fh:
            raw = json.load(fh)
        if not isinstance(raw, dict):
            raise ValueError("config/media.json root is not an object")
        # "$comment" and non-slice keys are ignored by the per-modality lookup.
        _defaults_cache = {k: v for k, v in raw.items() if k in MODALITIES and isinstance(v, dict)}
    except Exception as err:  # noqa: BLE001 — containment per GOV-RES-04
        _logger.warning("media warn: config/media.json unreadable (%s); using safe defaults", err)
        _defaults_cache = {}
    return _defaults_cache


# endregion


# region MED_* env overrides (DP-C §6.1 precedence tier 3)

_ENV = Mapping[str, Optional[str]]


def _env_overrides(modality: str, env: _ENV) -> MediaConfig:
    """Operator overrides for one slice from MED_* env vars. Empty/absent values
    are skipped so a partially-set env cannot blank a field."""
    m = modality.upper()
    out: MediaConfig = {}
    provider = env.get(f"MED_{m}_PROVIDER")
    secondary = env.get(f"MED_{m}_SECONDARY_PROVIDER")
    prompt = env.get(f"MED_{m}_PROMPT")
    ocr = env.get("MED_OCR_PROVIDER") if modality == "pdf" else None
    if provider:
        out["provider"] = provider
    if secondary:
        out["secondary_provider"] = secondary
    if prompt:
        out["prompt"] = prompt
    if ocr:
        out["ocr_provider"] = ocr
    return out


# endregion


# region Merge + validate + resolve (DP-C §6.1, §7.3)


def _compact(cfg: Optional[MediaConfig]) -> MediaConfig:
    """Drop None values so per-call overrides cannot shadow lower tiers with holes."""
    if not cfg:
        return {}
    return {k: v for k, v in cfg.items() if v is not None}


def _with_schema_defaults(merged: MediaConfig, modality: str) -> ResolvedMediaConfig:
    """Schema-declared defaults (DP-C §6.1), filled after merging.
    ocr_provider is PDF-only per the schema description — null elsewhere."""
    resolved: ResolvedMediaConfig = {
        "provider": merged["provider"],
        "secondary_provider": merged.get("secondary_provider", None),
        "timeout_ms": merged.get("timeout_ms", 15000),
        "retries": merged.get("retries", 1),
        "model": merged.get("model", None),
        "prompt": merged.get("prompt", None),
        "ocr_provider": (merged.get("ocr_provider", None) or "tesseract") if modality == "pdf" else None,
        "credentials_env": merged.get("credentials_env", ""),
    }
    if "options" in merged:
        resolved["options"] = merged["options"]
    return resolved


def load_media_config(
    modality: str,
    overrides: Optional[MediaConfig] = None,
    env: Optional[_ENV] = None,
) -> ResolvedMediaConfig:
    """Resolve one modality's MediaConfig: config/media.json slice < per-call
    `overrides` < MED_* env vars (lowest → highest, DP-C §6.1). The merged
    result is validated via RES-04 validate(media-config.schema); on failure a
    warn is logged and safe defaults returned (GOV-RES-02, DP-C §7.3).
    Never raises."""
    try:
        base = _load_defaults_file().get(modality) or {}
        env_map = os.environ if env is None else env
        merged: MediaConfig = {**base, **_compact(overrides), **_env_overrides(modality, env_map)}
        provider = merged.get("provider")
        if not provider or not isinstance(provider, str):
            # Schema requires provider; missing entirely means no usable source.
            _logger.warning("media warn: media config missing provider for %s; using safe defaults", modality)
            return _media_safe_defaults()
        resolved = _with_schema_defaults(merged, modality)
        result = validate(_schema(), resolved)
        if not result["valid"]:
            first = result["errors"][0] if result["errors"] else None
            path = first["path"] if first else "/"
            msg = first["message"] if first else "validation failed"
            _logger.warning("media warn: media config field %s invalid (%s); using safe defaults", path, msg)
            return _media_safe_defaults()
        return resolved
    except Exception as err:  # noqa: BLE001 — GOV-RES-04 containment
        _logger.warning("media warn: media config resolution failed (%s); using safe defaults", err)
        return _media_safe_defaults()


# endregion


# region Credential indirection (DP-C §6.1/§7.3 — NAME only, read at call time)


def resolve_credential(config: MediaConfig, env: Optional[_ENV] = None) -> str:
    """Read the credential VALUE at call time via the env var NAME held in
    credentials_env. Missing/empty value raises MediaError("missing_credentials")
    here — at call time — so RES-01 can retry/fallback (never at startup).
    An empty credentials_env means the provider needs no credential."""
    name = config.get("credentials_env") or ""
    if not name:
        return ""
    env_map = os.environ if env is None else env
    value = env_map.get(name)
    if value is None or value == "":
        raise MediaError("missing_credentials", f"credential env var {name} is not set")
    return value


# endregion
