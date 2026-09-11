# Requirement IDs: MED-03, MED-RES-01, MED-REU-01, GOV-MIN-04, GOV-RES-02, XCUT-08
"""openai-gpt4o-vision provider — Python mirror of openai-gpt4o-vision.ts
(DP-C §4.2 built-in).

Optional-dep style (GOV-MIN-04): the `openai` SDK is imported lazily on first
call; absent SDK or credential surfaces as a RAISED MediaError at call time so
RES-01 can retry/fallback — never a startup crash, never a swallowed error.
The credential VALUE is read via resolve_credential() using only the env var
NAME held in credentials_env (GOV-RES-02 indirection). Generic prompt only
(MED-REU-01); url inputs pass through as image_url.
"""

from __future__ import annotations

import base64 as _b64
from pathlib import Path
from typing import Any

from src.media.config import MediaError, resolve_credential

from .types import ImageInput, VisionOptions, VisionProvider, VisionResult, default_prompt

_MIME_BY_EXT = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}


def _to_image_url(input: ImageInput) -> str:
    """Materialize any input variant into an OpenAI image_url payload: remote
    urls pass through; path/buffer/base64 become data URIs."""
    if "url" in input:
        return str(input["url"])
    if "base64" in input:
        return f'data:{input.get("mime", "image/png")};base64,{input["base64"]}'
    if "buffer" in input:
        raw = bytes(input["buffer"])
        return f'data:{input.get("mime", "image/png")};base64,' + _b64.b64encode(raw).decode("ascii")
    ext = str(input["path"]).rsplit(".", 1)[-1].lower()
    mime = _MIME_BY_EXT.get(ext, "image/png")
    raw = Path(str(input["path"])).read_bytes()
    return f"data:{mime};base64," + _b64.b64encode(raw).decode("ascii")


class OpenaiGpt4oVisionProvider:
    id = "openai-gpt4o-vision"

    def caption(self, input: ImageInput, opts: VisionOptions | None = None) -> VisionResult:
        opts = opts or {}
        # Credential first (call-time check, GOV-RES-02) — raises MediaError(
        # "missing_credentials") when the named env var is unset.
        api_key = resolve_credential(
            {
                "provider": self.id,
                "credentials_env": opts.get("credentials_env") or "OPENAI_API_KEY",
            }
        )
        model = opts.get("model") or "gpt-4o"
        prompt = opts.get("prompt") or default_prompt()
        try:
            from openai import OpenAI  # lazy optional dependency (GOV-MIN-04)

            client = OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model=model,
                max_tokens=int(opts.get("maxTokens") or 300),
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": _to_image_url(input)}},
                        ],
                    }
                ],
            )
            choices = getattr(response, "choices", None) or []
            text = ""
            if choices:
                message = choices[0].message
                text = getattr(message, "content", None) or ""
            return VisionResult(
                text=str(text),
                confidence=0.9,  # chat.completions reports no confidence; neutral default
                structured={"objects": [], "dimensions": None, "prompt_used": prompt, "model": model},
            )
        except MediaError:
            raise
        except Exception as err:
            raise MediaError("provider_error", f"openai-gpt4o-vision caption failed: {err}") from err


_INSTANCE = OpenaiGpt4oVisionProvider()


def register() -> None:
    from .types import register_vision_provider

    register_vision_provider(_INSTANCE)
