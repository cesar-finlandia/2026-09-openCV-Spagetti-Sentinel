"""Public surface of the rationale module. DP-AGENT imports only `explain`."""
from app.rationale.client import BEDROCK_TIMEOUT_MS, budget_exhausted, explain
from app.rationale.history import MAX_PROMPT_TOKENS, WINDOW, build_history, estimate_tokens
from app.rationale.prompts import SYSTEM_PROMPT, USER_TEMPLATE, parse_response, render_user

__all__ = [
    "explain", "budget_exhausted", "BEDROCK_TIMEOUT_MS",
    "build_history", "estimate_tokens", "WINDOW", "MAX_PROMPT_TOKENS",
    "SYSTEM_PROMPT", "USER_TEMPLATE", "render_user", "parse_response",
]
