"""In-memory policy model used by the M1 decision engine.

The full YAML schema, loader, and shipped posture presets arrive in M2. M1
needs a frozen holder for: environment/data-class risk maps, risk weights,
agent profiles, ordered rules, and the escalation threshold. ``default_policy``
builds the balanced posture that ships with every install.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from agent_tooltrust.types import NormalizedCall

if TYPE_CHECKING:
    from agent_tooltrust.engine.argument_policy import ArgumentSpec

DEFAULT_POSTURE = "balanced"

#: Fields a leaf condition may constrain. Mirrors the flat ``Rule`` fields plus
#: the taxonomy-resolved ``tool_category`` and the action verb ``action``.
_CONDITION_FIELDS = frozenset(
    {"tool", "tool_category", "action", "environment", "data_class", "agent_class"}
)


def _validate_field(field_name: str) -> None:
    if field_name not in _CONDITION_FIELDS:
        raise ValueError(
            f"condition field must be one of {sorted(_CONDITION_FIELDS)}, "
            f"got {field_name!r}"
        )


@dataclass(frozen=True)
class Condition:
    """One node of a rule's boolean condition tree (M1, #93).

    A condition is either a **leaf** (``op`` in ``{"eq", "neq"}``, with a
    ``field`` and ``value``) or a **group** (``op`` in ``{"and", "or"}`` with
    ``conditions``, or ``"not"`` wrapping a single ``condition``). Both the
    flat ``Rule`` fields and the condition tree use the same comparison
    semantics: an ``action`` condition matches the verb *or* its action class.

    Attributes:
        op: ``eq`` / ``neq`` (leaf) or ``and`` / ``or`` / ``not`` (group).
        field: The call field a leaf compares (see ``_CONDITION_FIELDS``).
        value: The expected value for a leaf comparison.
        conditions: Child conditions for ``and`` / ``or`` groups.
        condition: The single child for a ``not`` group.
    """

    op: str
    field: str = ""
    value: str = "*"
    conditions: tuple[Condition, ...] = ()
    condition: Condition | None = None

    def __post_init__(self) -> None:
        if self.op == "not":
            if self.condition is None:
                raise ValueError("a 'not' condition requires a single `condition`")
            return
        if self.op in ("and", "or"):
            if not self.conditions:
                raise ValueError(f"a {self.op!r} group requires at least one child condition")
            return
        if self.op not in ("eq", "neq"):
            raise ValueError(f"unknown condition op {self.op!r}; use eq|neq|and|or|not")
        _validate_field(self.field)

    def matches(self, call: NormalizedCall) -> bool:
        """Evaluate this condition node against a normalized call."""
        if self.op == "and":
            return all(c.matches(call) for c in self.conditions)
        if self.op == "or":
            return any(c.matches(call) for c in self.conditions)
        if self.op == "not":
            if self.condition is None:
                # Unreachable given __post_init__, but fail safe rather than
                # attribute-error on a malformed manually-constructed node.
                return False
            return not self.condition.matches(call)
        return _leaf_matches(self.field, self.value, self.op, call)


def _leaf_value(field_name: str, call: NormalizedCall) -> str:
    """Read the call value a leaf condition compares against."""
    if field_name == "action":
        # An action condition matches the verb or its resolved action class,
        # mirroring the flat Rule.action semantics.
        return f"{call.action}\u0000{call.action_class}"
    return str(getattr(call, field_name))


def _leaf_matches(field_name: str, value: str, op: str, call: NormalizedCall) -> bool:
    actual = _leaf_value(field_name, call)
    if field_name == "action":
        verb, action_class = actual.split("\u0000", 1)
        matched = value in (verb, action_class)
        return matched if op == "eq" else not matched
    return (actual == value) if op == "eq" else (actual != value)


def condition_from_dict(data: dict[str, Any]) -> Condition:
    """Build a :class:`Condition` tree from a plain dict (policy schema form).

    A leaf dict carries ``field`` / ``op`` / ``value``; ``and``/``or`` groups
    carry a ``conditions`` list; ``not`` wraps a single ``condition`` dict.

    Args:
        data: The plain dict form of a condition clause.

    Returns:
        The equivalent frozen :class:`Condition` node.

    Raises:
        ValueError: On an unknown operator or malformed group shape.
    """
    op = data.get("op", "eq")
    if op == "not":
        try:
            child = data["condition"]
        except KeyError as exc:
            raise ValueError("a 'not' condition requires a `condition` dict") from exc
        return Condition(op="not", condition=condition_from_dict(child))
    if op in ("and", "or"):
        children = [condition_from_dict(c) for c in data.get("conditions", [])]
        return Condition(op=op, conditions=tuple(children))
    return Condition(op=op, field=str(data.get("field", "")), value=str(data.get("value", "*")))


@dataclass(frozen=True)
class AgentProfile:
    """Risk profile for one agent identity.

    ``environments`` is the identity's allowed environment scope (M2 #145,
    resource-scoped identity). An empty tuple means unrestricted — the
    identity may operate in any declared environment. A non-empty tuple is
    an allowlist: a call resolving to an environment outside it is denied by
    the engine's scope gate (default-deny), even before rule evaluation.
    """

    agent_class: str
    risk: float
    environments: tuple[str, ...] = ()
    parent: str | None = None

    def __post_init__(self) -> None:
        for env in self.environments:
            if not env.strip():
                raise ValueError("profile environments must be non-blank strings")


@dataclass(frozen=True)
class Rule:
    """A declarative policy rule.

    Each flat field acts as a constraint. ``"*"`` means "any". The ``action``
    constraint matches against both the verb (``call.action``) and the action
    class (``call.action_class``) so a rule written once for ``delete`` covers
    ``drop``, ``revoke``, and ``force_push``.

    ``conditions`` (M1 #93) is an optional boolean condition tree over
    :class:`Condition` nodes. When present, it is ANDed with the flat fields —
    all flat constraints plus the whole tree must match for the rule to match.
    An empty ``conditions`` list adds no constraint — a rule declares ``conditions``
    only when it wants extra gates, and omitting the field behaves exactly like
    a flat rule.
    """

    decision: str
    tool: str = "*"
    action: str = "*"
    environment: str = "*"
    data_class: str = "*"
    reason: str = ""
    conditions: tuple[Condition, ...] | tuple[dict[str, Any], ...] = ()
    obligations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        converted = tuple(
            cond if isinstance(cond, Condition) else condition_from_dict(cond)
            for cond in self.conditions
        )
        object.__setattr__(self, "conditions", converted)

    def matches(self, call: NormalizedCall) -> bool:
        if self.tool != "*" and self.tool != call.tool:
            return False
        if self.action != "*" and self.action not in (call.action, call.action_class):
            return False
        if self.environment != "*" and self.environment != call.environment:
            return False
        if self.data_class != "*" and self.data_class != call.data_class:
            return False
        conditions: tuple[Condition, ...] = self.conditions  # type: ignore[assignment]
        # An empty conditions list adds no constraint — consistent with the
        # flat-field wildcard default (same as `Rule(decision="...")`).
        if conditions:
            return all(c.matches(call) for c in conditions)
        return True


@dataclass(frozen=True)
class Policy:
    """The declarative policy governing decisions.

    Holds everything the scorer and decision stages consult:
    - ``environments`` / ``data_classes``: name → risk [0,1] maps. Names are
      matched exactly (case-sensitive); anything not declared scores at max
      risk (fail-closed).
    - ``risk_weights``: per-dimension weights for the aggregate score. A
      missing dimension defaults to weight 1.0.
    - ``rules``: ordered rule list. Resolution order is handled by the decide
      stage (deny > allow > escalate > band), not by list order.
    - ``agents``: identity → AgentProfile; ``default_agent`` is used for any
      id not listed.
    Note: M1 keeps ``version`` as a short string; M2 adds the YAML schema and
    loader that assigns real version semantics.
    """

    version: str
    posture: str
    environments: dict[str, float]
    data_classes: dict[str, float]
    risk_weights: dict[str, float]
    rules: tuple[Rule, ...]
    agents: dict[str, AgentProfile] = field(default_factory=dict)
    default_agent: AgentProfile = AgentProfile("general", 0.5)
    tool_visibility: dict[str, dict[str, tuple[str, ...]]] = field(default_factory=dict)
    args_policy: dict[str, dict[str, ArgumentSpec]] = field(default_factory=dict)

    def agent_profile(self, agent_id: str) -> AgentProfile:
        return self.agents.get(agent_id, self.default_agent)

    #: Conservative risk used when an environment is not declared: unknown
    #: environments are treated as high-risk (fail-closed), never as sandboxed.
    UNKNOWN_ENVIRONMENT_RISK = 1.0

    #: Conservative risk used when a data class is not declared.
    UNKNOWN_DATA_CLASS_RISK = 1.0


def _trim(v: dict[str, float]) -> dict[str, float]:
    return {k: max(0.0, min(1.0, float(v))) for k, v in v.items()}


def default_policy(posture: str = DEFAULT_POSTURE) -> Policy:
    """Build the shipped default policy for a posture preset.

    ``balanced`` is the default. ``strict`` denies anything destructive in any
    environment; ``permissive`` only blocks the most destructive operations.
    """
    posture = posture if posture in ("strict", "balanced", "permissive") else DEFAULT_POSTURE

    environments: dict[str, float] = {
        "development": 0.0,
        "staging": 0.1,
        "pre_prod": 0.4,
        "production": 0.7,
    }
    data_classes: dict[str, float] = {
        "public": 0.0,
        "internal": 0.2,
        "restricted": 0.5,
        "customer_pii": 1.0,
    }
    agents: dict[str, AgentProfile] = {
        "release-bot": AgentProfile("ci-bot", 0.1),
        "ci-bot": AgentProfile("ci-bot", 0.1),
        "dev-eng": AgentProfile("engineer", 0.3),
        "data-sci": AgentProfile("engineer", 0.3),
    }

    base_rules: list[Rule] = [
        Rule(
            decision="deny",
            action="delete",
            environment="production",
            reason="Deletes in production are blocked.",
        ),
        Rule(decision="deny", action="grant", reason="Grant operations always require review."),
        Rule(
            decision="escalate",
            action="write",
            environment="production",
            reason="Write actions in production require approval.",
        ),
    ]

    if posture == "balanced":
        rules = base_rules
    elif posture == "strict":
        rules = [
            Rule(decision="deny", action="delete", reason="Deletes are blocked by default."),
            Rule(decision="deny", action="grant", reason="Grant operations are always blocked."),
            Rule(
                decision="deny",
                action="write",
                environment="production",
                reason="Writes in production are blocked under strict policy.",
            ),
            Rule(
                decision="escalate",
                action="write",
                reason="Write actions require approval under strict policy.",
            ),
        ]
        environments = {"development": 0.0, "staging": 0.1, "production": 0.7}
    else:  # permissive
        rules = [
            Rule(
                decision="deny",
                action="delete",
                environment="production",
                reason="Deletes in production are blocked.",
            ),
            Rule(decision="deny", action="grant", reason="Grant operations require review."),
            Rule(
                decision="escalate",
                action="write",
                environment="production",
                reason="Write actions in production require approval.",
            ),
        ]

    return Policy(
        version="1.0.0",
        posture=posture,
        environments=_trim(environments),
        data_classes=_trim(data_classes),
        risk_weights={
            "tool_category": 1.0,
            "action_class": 1.0,
            "environment": 1.0,
            "data_sensitivity": 1.0,
            "agent_class": 1.0,
        },
        rules=tuple(rules),
        agents=agents,
    )
