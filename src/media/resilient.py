# Requirement IDs: MED-RES-01, MED-03, RES-01, RES-03, RES-REU-02, GOV-RES-01, XCUT-08
"""Optional ergonomic sugar for wiring media wrappers into RES-01 (DP-C §7.1).

with_media_resilience(fn, secondary_fn=None, resilience_config=None) delegates
to src.resilience.with_resilience; the secondary provider callable is passed
out-of-band via deps["secondary_provider"] (DP-A §4.2, never serialized).

Default resilience config per DP-C §7.1: {timeout_ms:15000, retries:1,
fallback_chain:{order:["secondary_provider","cache","replay","none"]}}. The
secondary_provider STEP is explicitly enabled because DP-A defaults it to
disabled — without {"enabled": True} the chain would skip straight to cache.

Consumers may use with_resilience directly — this helper is sugar only.
Domain-free (GOV-REU-02); no modality-specific imports (MED-REU-02).
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Mapping, Optional

from src.resilience.wrapper import with_resilience

DEFAULT_MEDIA_RESILIENCE_CONFIG: Dict[str, Any] = {
    "timeout_ms": 15000,
    "retries": 1,
    "fallback_chain": {
        "order": ["secondary_provider", "cache", "replay", "none"],
        # DP-A defaults this step to enabled:False; media wants it ON when a
        # secondary_fn is supplied.
        "secondary_provider": {"enabled": True},
    },
}


def with_media_resilience(
    fn: Callable[..., Any],
    secondary_fn: Optional[Callable[..., Any]] = None,
    resilience_config: Optional[Mapping[str, Any]] = None,
) -> Callable[..., Any]:
    """Wrap a media closure (`fn() -> UnifiedMediaMessage`, zero required args —
    RES-REU-02) with timeout+retry+fallback.

    - ``fn``               primary call, e.g. ``lambda: transcribe(input, primary_opts)``
    - ``secondary_fn``     optional RES-03 secondary-provider call with identical
                           I/O shape (e.g. alternate provider id); passed
                           out-of-band via deps.secondary_provider
    - ``resilience_config`` optional override; defaults to
                           DEFAULT_MEDIA_RESILIENCE_CONFIG

    Returns a callable resolving to the message on success or a DegradedResult
    dict once every fallback step is exhausted — never raises unhandled
    (RES-RES-03).
    """
    deps: Optional[Dict[str, Any]] = (
        {"secondary_provider": secondary_fn} if secondary_fn is not None else None
    )
    return with_resilience(fn, resilience_config if resilience_config is not None else DEFAULT_MEDIA_RESILIENCE_CONFIG, deps)
