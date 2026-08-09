"""In-memory policy model used by the M1 decision engine.

The full YAML schema, loader, and shipped posture presets arrive in M2. M1
needs a frozen holder for: environment/data-class risk maps, risk weights,
agent profiles, ordered rules, and the escalation threshold. ``default_policy``
builds the balanced posture that ships with every install.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agent_tooltrust.types import NormalizedCall

DEFAULT_POSTURE = "balanced"


@dataclass(frozen=True)
class AgentProfile:
    """Risk profile for one agent identity."""

    agent_class: str
    risk: float


@dataclass(frozen=True)
class Rule:
    """A declarative policy rule.

    Each field acts as a constraint. ``"*"`` means "any". The ``action``
    constraint matches against both the verb (``call.action``) and the action
    class (``call.action_class``) so a rule written once for ``delete`` covers
    ``drop``, ``revoke``, and ``force_push``.
    """

    decision: str
    tool: str = "*"
    action: str = "*"
    environment: str = "*"
    data_class: str = "*"
    reason: str = ""

    def matches(self, call: NormalizedCall) -> bool:
        if self.tool != "*" and self.tool != call.tool:
            return False
        if self.action != "*" and self.action not in (call.action, call.action_class):
            return False
        if self.environment != "*" and self.environment != call.environment:
            return False
        if self.data_class != "*" and self.data_class != call.data_class:
            return False
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
