# Requirement IDs: MED-03, MED-RES-01, MED-REU-01, GOV-MIN-04, GOV-RES-02, XCUT-08
"""anthropic-claude-vision provider — Python mirror of
anthropic-claude-vision.ts (DP-C §4.2 built-in, secondary per §6.4).

Optional-dep style (GOV-MIN-04): the `anthropic` SDK is imported lazily on
first call; a missing credential raises MediaError("missing_credentials") AT
CALL TIME so RES-01 can retry/fallback — never a startup crash (§7.3).
Credential VALUE read via resolve_credential() using only the env var NAME in
credentials_env (GOV-RES-02 indirection). Generic prompt only (MED-REU-01).
"""

from __future__ import annotations

import base64 as _b64
from pathlib import Path
from typing import Any

from src.media.config import MediaError, resolve_credential

from .types import ImageInput, VisionOptions, VisionProvider, VisionResult, default_prompt

_MIME_BY_EXT = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}


def _to_image_source(input: ImageInput) -> dict[str, Any]:
    """Materialize any input variant into an Anthropic image source block:
    remote urls pass through; path/buffer/base64 become base64 sources."""
    if "url" in input:
        return {"type": "url", "url": str(input["url"])}
    if "base64" in input:
        return {"type": "base64", "media_type": input.get("mime", "image/png"), "data": input["base64"]}
    if "buffer" in input:
        raw = bytes(input["buffer"])
        return {
            "type": "base64",
            "media_type": input.get("mime", "image/png"),
            "data": _b64.b64encode(raw).decode("ascii"),
        }
    ext = str(input["path"]).rsplit(".", 1)[-1].lower()
    mime = _MIME_BY_EXT.get(ext, "image/png")
    raw = Path(str(input["path"])).read_bytes()
    return {
        "type": "base64",
        "media_type": mime,
        "data": _b64.b64encode(raw).decode("ascii"),
    }


class AnthropicClaudeVisionProvider:
    id = "anthropic-claude-vision"

    def caption(self, input: ImageInput, opts: VisionOptions | None = None) -> VisionResult:
        opts = opts or {}
        # Credential first (call-time check, GOV-RES-02/§7.3) — raises MediaError(
        # "missing_credentials") when the named env var is unset.
        api_key = resolve_credential(
            {
                "provider": self.id,
                "credentials_env": opts.get("credentials_env") or "ANTHROPIC_API_KEY",
            }
        )
        model = opts.get("model") or "claude-3-5-sonnet-latest"
        prompt = opts.get("prompt") or default_prompt()
        try:
            import anthropic  # lazy optional dependency (GOV-MIN-04)

            client = anthropic.Anthropic(api_key=api_key)
            response = client.messages.create(
                model=model,
                max_tokens=int(opts.get("maxTokens") or 300),
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "image", "source": _to_image_source(input)},
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
            )
            blocks = getattr(response, "content", None) or []
            text = "\n".join(
                getattr(block, "text", "") for block in blocks if getattr(block, "type", "") == "text"
            )
            return VisionResult(
                text=str(text),
                confidence=0.9,  # messages API reports no confidence; neutral default
                structured={"objects": [], "dimensions": None, "prompt_used": prompt, "model": model},
            )
        except MediaError:
            raise
        except Exception as err:
            raise MediaError("provider_error", f"anthropic-claude-vision caption failed: {err}") from err


_INSTANCE = AnthropicClaudeVisionProvider()


def register() -> None:
    from .types import register_vision_provider

    register_vision_provider(_INSTANCE)
