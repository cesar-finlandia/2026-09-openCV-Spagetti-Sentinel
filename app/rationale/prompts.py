"""Prompt assembly. The literal template text lives in templates/*.md and is loaded once."""
from __future__ import annotations

from pathlib import Path

from app.contracts.types import AgentDecision, VisionScores

_SYSTEM_PATH = Path(__file__).parent / "templates" / "system.md"
_USER_PATH = Path(__file__).parent / "templates" / "user.md"

SYSTEM_PROMPT: str = _SYSTEM_PATH.read_text(encoding="utf-8")
USER_TEMPLATE: str = _USER_PATH.read_text(encoding="utf-8")


def render_user(decision: AgentDecision, scores: VisionScores,
                history: list[VisionScores]) -> str:
    """Fill USER_TEMPLATE. Numbers formatted to 2 decimals; history as compact table."""
    try:
        rows = []
        for h in history:
            try:
                rows.append(
                    f"| {h.get('frame_index')} | {h.get('t_ms', 0) / 1000.0:.1f} | "
                    f"{h.get('spaghetti_score', 0.0):.2f} | {h.get('confidence', 0.0):.2f} |"
                )
            except Exception:
                continue
        table = "\n".join(rows) if rows else "| - | - | - | - |"
        t_s = f"{scores.get('t_ms', 0) / 1000.0:.1f}"
        return USER_TEMPLATE.format(
            frame_index=decision.get("frame_index", scores.get("frame_index", 0)),
            t_s=t_s,
            spaghetti_score=f"{scores.get('spaghetti_score', 0.0):.2f}",
            threshold=f"{decision.get('threshold', 0.0):.2f}",
            confidence=f"{scores.get('confidence', 0.0):.2f}",
            first_layer_coverage=f"{scores.get('first_layer_coverage', 0.0):.2f}",
            edge_regularity=f"{scores.get('edge_regularity', 0.0):.2f}",
            motion_energy=f"{scores.get('motion_energy', 0.0):.2f}",
            texture_disorder=f"{scores.get('texture_disorder', 0.0):.2f}",
            history_table=table,
            action=decision.get("action", ""),
            reason_code=decision.get("reason_code", ""),
            requires_human=decision.get("requires_human", False),
        )
    except Exception:
        return USER_TEMPLATE


def parse_response(raw: str) -> tuple[str, list[str]]:
    """Split the model's reply into (rationale_paragraph, checklist_items)."""
    try:
        if raw is None:
            return ("", [])
        text = str(raw).strip()
        if not text:
            return ("", [])
        lines = text.splitlines()
        # Find checklist divider.
        idx = None
        for i, ln in enumerate(lines):
            s = ln.strip().lower()
            if s == "checklist:" or s.startswith("checklist"):
                # Require it to look like a header (short line).
                if len(s) < 24:
                    idx = i
                    break
        if idx is not None:
            rat_lines = lines[:idx]
            chk_lines = lines[idx + 1:]
        else:
            rat_lines = []
            chk_lines = []
            bullet_prefix = ("-", "*", "•")
            for ln in lines:
                s = ln.strip()
                if s.startswith(bullet_prefix) or _is_numbered(s):
                    chk_lines.append(ln)
                elif not chk_lines:
                    rat_lines.append(ln)
                else:
                    # Trailing non-bullet after bullets: treat as rationale overflow? keep as checklist skip
                    continue
            if not chk_lines:
                # No bullets at all: whole text is rationale.
                rat = " ".join(l.strip() for l in lines if l.strip())
                rat = " ".join(rat.split())
                return (rat[:600].strip(), [])
        items: list[str] = []
        for ln in chk_lines:
            s = ln.strip()
            if not s:
                continue
            if s.startswith(("-", "*", "•")):
                s = s[1:].strip()
            elif _is_numbered(s):
                # strip "1. " / "2) "
                import re

                s = re.sub(r"^\d+[.)]\s*", "", s).strip()
            else:
                # Non-bullet line inside checklist block: keep if non-empty.
                pass
            if s:
                items.append(s[:120])
            if len(items) >= 6:
                break
        rat = " ".join(l.strip() for l in rat_lines if l.strip())
        rat = " ".join(rat.split())
        return (rat[:600].strip(), items)
    except Exception:
        try:
            return (str(raw)[:600], [])
        except Exception:
            return ("", [])


def _is_numbered(s: str) -> bool:
    import re

    return bool(re.match(r"^\d+[.)]\s+\S", s))
