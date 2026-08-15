"""M2.2 — load, validate, and merge policies (#2, F-60).

Merge order (late wins):
1. ``default_policy(posture)`` — the shipped posture preset,
2. the org ``tooltrust.yaml`` overlay.

Dict-style sections (``environments``, ``data_classes``, ``risk_weights``)
are merged per-key so an org only overrides what it declares. ``rules`` are
replaced wholesale if the org declares any; an org that writes rules is
explicitly taking over its governance list. ``agents`` always come from the
preset — the schema has no agent section.

Every failure path raises :class:`PolicyParseError` (fail-closed,
``DENY_POLICY_PARSE_ERROR``) with the offending ``line:column`` so ``tooltrust
check`` can point operators at the exact problem, matching "Validate on load"
in architecture §3.1.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from agent_tooltrust.engine.argument_policy import ArgumentSpec
from agent_tooltrust.errors import PolicyParseError
from agent_tooltrust.policy.models import Policy, Rule, default_policy
from agent_tooltrust.policy.schema import PolicyDocument, parse_tooltrust_yaml


def _first_line_column(text: str, loc: tuple[str | int, ...]) -> tuple[int, int]:
    """Resolve a pydantic error ``loc`` to its YAML line:column.

    Walks the composed YAML node tree (which carries source marks) following
    the location path, so a violation like ``environments[production].
    criticality`` points at the actual offending value's line, and the pydantic
    violation captured to the value node."""
    doc = yaml.compose(text)
    node = doc
    for step in loc:
        if node is None:
            break
        if isinstance(step, int):
            if isinstance(node, yaml.SequenceNode) and step < len(node.value):
                node = node.value[step]
            else:
                node = None
        elif isinstance(node, yaml.MappingNode):
            node = next(
                (pair[1] for pair in node.value if pair[0].value == step),
                None,
            )
        else:
            node = None
    if node is not None and node.start_mark is not None:
        return node.start_mark.line + 1, node.start_mark.column + 1
    return 1, 1


def _schema_error_message(error: ValidationError, text: str) -> str:
    """Build a human-readable error message from a pydantic ValidationError.

    Resolves the offending field's YAML line/column and produces a single-line
    message suitable for ``tooltrust check`` output.

    Args:
        error: Pydantic ``ValidationError`` caught during parsing.
        text: Raw YAML text for line/column lookup.

    Returns:
        A string like ``"line 3, column 12: invalid environments.production.criticality: ..."``.
    """
    first = error.errors(include_url=False)[0]
    line, column = _first_line_column(text, tuple(first["loc"]))
    where = ".".join(str(part) for part in first["loc"])
    return f"line {line}, column {column}: invalid {where}: {first['msg']}"


def _condition_dicts(conds: list[Any]) -> list[dict[str, Any]]:
    """Convert validated :class:`ConditionSpec` objects to plain dicts.

    The in-memory :class:`~agent_tooltrust.policy.models.Condition` is built
    from dicts (``condition_from_dict``); this helper rehydrates the pydantic
    specs into that shape so the model stays the single evaluation home.

    Args:
        conds: The validated condition specs from a policy rule.

    Returns:
        Plain-dict condition clauses for ``condition_from_dict``.
    """
    out: list[dict[str, Any]] = []
    for spec in conds:
        if spec.op in ("and", "or"):
            out.append({"op": spec.op, "conditions": _condition_dicts(spec.conditions)})
        elif spec.op == "not" and spec.condition is not None:
            out.append({"op": "not", "condition": _condition_dicts([spec.condition])[0]})
        else:
            out.append({"op": spec.op, "field": spec.field, "value": spec.value})
    return out


def _build_policy(doc: PolicyDocument) -> Policy:
    """Merge a validated :class:`PolicyDocument` onto the posture default.

    Dict fields (environments, data_classes, risk_weights) are merged per-key
    so the org only overrides what it declares. Rules are replaced wholesale
    when the org declares any non-empty list. Agents always come from the
    posture preset (schema has no agents field).

    Args:
        doc: The validated org ``tooltrust.yaml`` document.

    Returns:
        A fully resolved :class:`Policy` ready for the engine.
    """
    base = default_policy(doc.posture)
    environments = base.environments | {
        name: env.criticality for name, env in doc.environments.items()
    }
    data_classes = base.data_classes | {
        name: dc.sensitivity for name, dc in doc.data_classes.items()
    }
    risk_weights = base.risk_weights | doc.risk_weights
    rules = (
        tuple(
            Rule(
                decision=rule.decision,
                tool=rule.tool,
                action=rule.action,
                environment=rule.environment,
                data_class=rule.data_class,
                reason=rule.reason,
                conditions=tuple(_condition_dicts(rule.conditions)),
                obligations=tuple(rule.obligations),
            )
            for rule in doc.rules
        )
        if doc.rules
        else base.rules
    )
    tool_visibility: dict[str, dict[str, tuple[str, ...]]] = {}
    args_policy: dict[str, dict[str, ArgumentSpec]] = {}
    for spec in doc.tools:
        if spec.hidden_for:
            tool_visibility[spec.name] = {"hidden_for": tuple(spec.hidden_for)}
        if spec.args_policy:
            args_policy[spec.name] = {
                name: ArgumentSpec(
                    required=arg.required,
                    forbid=tuple(arg.forbid),
                    min=arg.min,
                    max=arg.max,
                    allowed=tuple(arg.allowed),
                )
                for name, arg in spec.args_policy.items()
            }
    return Policy(
        version=doc.version,
        posture=doc.posture,
        environments=environments,
        data_classes=data_classes,
        risk_weights=risk_weights,
        rules=rules,
        agents=base.agents,
        default_agent=base.default_agent,
        tool_visibility=tool_visibility,
        args_policy=args_policy,
    )


def load_policy_text(text: str) -> Policy:
    """Parse, validate, and merge the contents of a tooltrust.yaml document.

    Args:
        text: The raw YAML source of ``tooltrust.yaml``.

    Returns:
        A fully resolved :class:`Policy` with the org overlay merged onto the
        posture default.

    Raises:
        PolicyParseError: YAML syntax errors or schema violations are converted
            to this exception with the offending line:column.
    """
    try:
        doc = parse_tooltrust_yaml(text)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        if mark is not None:
            raise PolicyParseError(
                f"line {mark.line + 1}, column {mark.column + 1}: {exc}"
            ) from exc
        raise PolicyParseError(str(exc)) from exc
    except ValidationError as exc:
        raise PolicyParseError(_schema_error_message(exc, text)) from exc
    except ValueError as exc:
        raise PolicyParseError(str(exc)) from exc
    try:
        return _build_policy(doc)
    except (ValueError, ValidationError) as exc:
        # Model construction (e.g. a malformed ``conditions`` tree: unknown op,
        # a ``not`` without a child, an unknown condition field) raises after
        # the pydantic schema pass. Convert to the same fail-closed
        # PolicyParseError contract so every load failure is a clean error.
        raise PolicyParseError(str(exc)) from exc


def load_policy(path: str | Path) -> Policy:
    """Load a policy from *path*.

    A missing file or a directory is a :class:`PolicyParseError` — the engine
    must never run against a policy it could not read.

    Args:
        path: Filesystem path to ``tooltrust.yaml``.

    Returns:
        A fully resolved :class:`Policy`.

    Raises:
        PolicyParseError: The file does not exist, is a directory, is
            unreadable, or contains invalid YAML/policy data.
    """
    file = Path(path)
    try:
        text = file.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise PolicyParseError(f"no such policy file: {file}") from exc
    except IsADirectoryError as exc:
        raise PolicyParseError(f"policy path is a directory, not a file: {file}") from exc
    except OSError as exc:
        raise PolicyParseError(f"cannot read policy file {file}: {exc}") from exc
    return load_policy_text(text)
