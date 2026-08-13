"""Stage 1 of the pipeline: normalize a raw tool call.

Canonicalizes tool names, action verbs, environment, data class, and agent id:
whitespace collapse, Unicode NFKC, case folding, and confusable-character
transliteration for adversarial lookalike attacks (F-89 P0). An unknown tool
raises :class:`UnknownToolError`; a malformed call raises
:class:`MalformedInputError`. The engine's fail-closed handler converts those
into deny decisions — stages 2-5 never run.

Canonicalization contract (important):
- The *tool name* is aggressively canonicalized (case-folded + confusables)
  because it is attacker-visible and matched against the taxonomy registry.
- *environment / data_class / agent_id* are org-defined configuration keys.
  They are only whitespace-collapsed, NOT case-folded: ``Production`` is a
  different key than ``production`` and resolves as unknown → fail-closed
  (score 1.0, then deny). Losing this by lowercasing would be a safety bug.
- *action verbs* are whitespace-collapsed but NOT case-folded. An unseen verb
  (e.g. ``GET``) resolves conservatively to ``write`` via the taxonomy, never
  to a zero-risk read.
"""

from __future__ import annotations

import unicodedata
from typing import Any, cast

from agent_tooltrust.errors import MalformedInputError, UnknownToolError
from agent_tooltrust.taxonomy import action_class_for, domain_for
from agent_tooltrust.types import ActionClass, NormalizedCall

#: Characters that look like ASCII but are distinct Unicode code points
#: (Cyrillic, Greek, Ukrainian, etc.). NFKC does not fold these, so we
#: transliterate the common confusables directly after case folding.
CONFUSABLES: dict[str, str] = {
    # Cyrillic → Latin (lowercase pairing after fold)
    "а": "a",
    "е": "e",
    "о": "o",
    "р": "p",
    "с": "c",
    "у": "y",
    "х": "h",
    "і": "i",
    "ѕ": "s",
    "ј": "j",
    "ӏ": "l",
    "ɡ": "g",
    "ԁ": "d",
    "ƿ": "n",
    "г": "r",
    "м": "m",
    "т": "t",
    "н": "h",
    # Greek → Latin
    "α": "a",
    "ε": "e",
    "ο": "o",
    "ρ": "p",
    "υ": "y",
    "χ": "h",
    "ι": "i",
    "σ": "o",
}


def _fold_whitespace(value: str) -> str:
    return " ".join(value.split())


def _normalize_tool_name(name: str) -> str:
    """Canonicalize a tool name against confusable-character attacks.

    Order matters: NFKC (composed/fullwidth forms) → case fold → confusable
    transliteration → whitespace collapse → strip. A name that is blank after
    folding is malformed.
    """
    folded = unicodedata.normalize("NFKC", name)
    folded = folded.casefold()
    folded = folded.replace("\u200b", "").replace("\u200c", "").replace("\u200d", "")
    transliterated = "".join(CONFUSABLES.get(ch, ch) for ch in folded)
    folded = _fold_whitespace(transliterated).strip()
    if not folded:
        raise MalformedInputError("tool name is blank after normalization")
    return folded


def normalize(
    tool: str,
    action: str,
    environment: str,
    data_class: str,
    agent_id: str,
    agent_class: str = "general",
    session_id: str | None = None,
    arguments: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
) -> NormalizedCall:
    """Canonicalize a raw tool call into a :class:`NormalizedCall`.

    Raises :class:`UnknownToolError` when *tool* is not in the taxonomy and
    :class:`MalformedInputError` when any required field is blank or not a
    string. The engine's fail-closed handler maps those exceptions to deny
    decisions, so a hostile or malformed call can never surface a raw
    ``TypeError``/``AttributeError`` past the boundary.
    """
    for label, value in (
        ("tool", tool),
        ("action", action),
        ("environment", environment),
        ("data_class", data_class),
        ("agent_id", agent_id),
        ("agent_class", agent_class),
    ):
        if not isinstance(value, str) or not value.strip():
            raise MalformedInputError(f"{label} must be a non-blank string")

    canonical_tool = _normalize_tool_name(tool)
    domain = domain_for(canonical_tool)
    if domain is None:
        raise UnknownToolError(canonical_tool)

    canonical_action = _fold_whitespace(action).strip()
    action_class: ActionClass = cast(ActionClass, action_class_for(canonical_action))

    return NormalizedCall(
        tool=canonical_tool,
        tool_category=domain,
        action=canonical_action,
        action_class=action_class,
        environment=_fold_whitespace(environment).strip(),
        data_class=_fold_whitespace(data_class).strip(),
        agent_id=_fold_whitespace(agent_id).strip(),
        agent_class=_fold_whitespace(agent_class).strip() or "general",
        session_id=session_id,
        arguments=arguments,
        context=context,
    )
