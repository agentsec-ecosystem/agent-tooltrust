"""Stage 1b of the pipeline — argument-level policy (M1 #142, DD-15).

Tool-selection policy decides *whether* a tool may be called; argument-level
policy constrains *how* it may be called. A per-tool ``args_policy`` declares
required arguments, forbidden substrings, numeric bounds, and allowed values.
Evaluation is pure and deterministic (regex/allowlist/range — never an LLM
judgment), so identical inputs produce identical decisions every run.

Semantics (documented, per DD-15):
- ``required``: the argument must be present in the call.
- ``forbid``: any pattern that appears as a *substring* of the argument's
  string form is a violation; the empty string additionally matches only the
  empty value, so specifying ``forbid: [""]`` rejects blank while allowing
  real content.
- ``min`` / ``max``: inclusive numeric bounds on the argument.
- ``allowed``: the value must be one of the listed strings.
- A missing non-required argument and any argument with no corresponding spec
  pass through — the schema constrains, it does not allowlist.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ArgumentSpec:
    """Declarative constraints on one tool-call argument.

    Attributes:
        required: The argument must be present (non-``None``).
        forbid: Substrings that must not appear in the argument.
        min: Inclusive lower numeric bound.
        max: Inclusive upper numeric bound.
        allowed: The exact values the argument may take (when non-empty).
    """

    required: bool = False
    forbid: tuple[str, ...] = ()
    min: float | None = None
    max: float | None = None
    allowed: tuple[str, ...] = ()


def _forbidden(value: Any, forbid: tuple[str, ...]) -> bool:
    text = str(value)
    for pattern in forbid:
        if pattern == "":
            if text == "":
                return True
        elif pattern in text:
            return True
    return False


def _out_of_range(value: Any, spec: ArgumentSpec) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    if spec.min is not None and number < spec.min:
        return True
    if spec.max is not None and number > spec.max:
        return True
    return False


def _not_allowed(value: Any, spec: ArgumentSpec) -> bool:
    if not spec.allowed:
        return False
    return str(value) not in spec.allowed


def check_arguments(
    tool: str,
    arguments: dict[str, Any] | None,
    args_policy: dict[str, dict[str, ArgumentSpec]],
) -> str | None:
    """Validate a tool call's arguments against the per-tool policy.

    Args:
        tool: The canonical tool name.
        arguments: The call's argument mapping (may be ``None``).
        args_policy: Tool → {argument → spec}.

    Returns:
        The name of the first violating argument, or ``None`` if the call
        passes argument-level policy.
    """
    specs = args_policy.get(tool)
    if not specs:
        return None
    arguments = arguments or {}
    for name, spec in specs.items():
        if name not in arguments or arguments[name] is None:
            if spec.required:
                return name
            continue
        value = arguments[name]
        if _forbidden(value, spec.forbid):
            return name
        if _out_of_range(value, spec):
            return name
        if _not_allowed(value, spec):
            return name
    return None
