"""M2.1 — the tooltrust.yaml policy schema (#1, F-06/F-60).

Pydantic v2 models for the policy document defined in architecture §5.4.
Parsing is strict: unknown keys are rejected (``extra="forbid"``), risk
values are bounded to [0, 1], and enrichments like ``audit``/``escalation``
have sane defaults so an org file only needs to override what it cares about.

This module only *validates*; turning a validated policy into the in-memory
:class:`~agent_tooltrust.policy.models.Policy` consumed by the engine (with
default-posture merging) is the loader's job (M2.2).
"""

from __future__ import annotations

from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Posture = Literal["strict", "balanced", "permissive"]
RuleDecision = Literal["allow", "audit", "escalate", "deny"]
AuditSink = Literal["jsonl", "sqlite", "postgres"]

#: Fields a leaf condition may constrain. Mirrors the flat ``Rule`` fields plus
#: the taxonomy-resolved ``tool_category`` and the action verb ``action``.
_CONDITION_FIELDS = frozenset(
    {"tool", "tool_category", "action", "environment", "data_class", "agent_class"}
)

#: The five scored dimensions. risk_weights keys are restricted to these so a
#: typo like ``tool_categry`` is caught at load time instead of silently
#: contributing nothing to the aggregate (score() iterates these exact names).
KNOWN_DIMENSIONS = frozenset(
    {"tool_category", "action_class", "environment", "data_sensitivity", "agent_class"}
)


def _in_unit(value: float, mode: str) -> float:
    """Raise ValueError unless *value* is in the [0, 1] risk range.

    Args:
        value: The numeric value to validate.
        mode: Human-readable field name for error messages (e.g., ``"criticality"``).

    Returns:
        *value* unchanged if valid.

    Raises:
        ValueError: If *value* is outside [0, 1].
    """
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{mode} must be in [0, 1], got {value}")
    return value


class EnvironmentSpec(BaseModel):
    """One environment's risk mapping: name -> criticality score."""

    model_config = ConfigDict(extra="forbid")

    criticality: float = Field(description="Environment criticality in [0, 1]")

    @field_validator("criticality")
    @classmethod
    def _check_criticality(cls, v: float) -> float:
        return _in_unit(v, "criticality")


class DataClassSpec(BaseModel):
    """One data class's risk mapping: name -> sensitivity score."""

    model_config = ConfigDict(extra="forbid")

    sensitivity: float = Field(description="Data sensitivity in [0, 1]")

    @field_validator("sensitivity")
    @classmethod
    def _check_sensitivity(cls, v: float) -> float:
        return _in_unit(v, "sensitivity")


class ConditionSpec(BaseModel):
    """One node of a rule's boolean condition tree (M1 #93).

    Mirrors :class:`~agent_tooltrust.policy.models.Condition`. A leaf carries
    ``field`` / ``op`` (``eq``/``neq``) / ``value``; an ``and``/``or`` group
    carries ``conditions``; a ``not`` carries a single ``condition``. Unknown
    keys are rejected so a typo like ``valu`` is caught at load time. ``op``
    is restricted to the known operators, so ``op: xor`` is a schema error
    with a line:column, not a crash during model construction.
    """

    model_config = ConfigDict(extra="forbid")

    op: Literal["eq", "neq", "and", "or", "not"] = "eq"
    field: str = ""
    value: str = "*"
    conditions: list[ConditionSpec] = Field(default_factory=list)
    condition: ConditionSpec | None = None

    @model_validator(mode="after")
    def _check_shape(self) -> ConditionSpec:
        if self.op in ("and", "or") and not self.conditions:
            raise ValueError(f"a {self.op!r} group requires at least one child condition")
        if self.op == "not" and self.condition is None:
            raise ValueError("a 'not' condition requires a single `condition`")
        if self.op in ("eq", "neq") and self.field not in _CONDITION_FIELDS:
            raise ValueError(
                f"condition field must be one of {sorted(_CONDITION_FIELDS)}, "
                f"got {self.field!r}"
            )
        return self


class RuleSpec(BaseModel):
    """One declarative rule. ``"*"`` means "match anything".

    Field names match the in-memory :class:`Rule` and the architecture §5.4
    example. ``decision`` accepts all four decisions; note the decide stage
    only *enforces* deny > allow > escalate rules and produces ``audit`` from
    the risk band, but org files may still carry an ``audit`` rule for
    documentation/forward-compat.

    ``conditions`` (M1 #93) is an optional boolean condition tree ANDed with
    the flat constraints. It accepts a list of :class:`ConditionSpec` clauses.
    """

    model_config = ConfigDict(extra="forbid")

    decision: RuleDecision
    tool: str = "*"
    action: str = "*"
    environment: str = "*"
    data_class: str = "*"
    reason: str = ""
    conditions: list[ConditionSpec] = Field(default_factory=list)
    obligations: list[str] = Field(
        default_factory=list,
        description="Mandatory gatekeeper-enforced side-effects (M1 #147)",
    )

    @field_validator("obligations")
    @classmethod
    def _check_obligations(cls, v: list[str]) -> list[str]:
        from agent_tooltrust.engine.obligations import OBLIGATION_NAMES

        unknown = sorted(set(v) - set(OBLIGATION_NAMES))
        if unknown:
            raise ValueError(f"unknown obligation(s): {', '.join(unknown)}")
        return v

    @model_validator(mode="after")
    def _check_obligations_on_allow_only(self) -> RuleSpec:
        if self.obligations and self.decision != "allow":
            raise ValueError(
                f"obligations are only enforced on 'allow' rules, "
                f"got decision {self.decision!r}"
            )
        return self


class EscalationConfig(BaseModel):
    """Approval-escalation tuning."""

    model_config = ConfigDict(extra="forbid")

    threshold: float = 0.5
    ttl_seconds: int = 300

    @field_validator("threshold")
    @classmethod
    def _check_threshold(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"threshold must be in [0, 1], got {v}")
        return v

    @field_validator("ttl_seconds")
    @classmethod
    def _check_ttl(cls, v: int) -> int:
        if v <= 0:
            raise ValueError(f"ttl_seconds must be positive, got {v}")
        return v


class AuditConfig(BaseModel):
    """Audit sink configuration (consumed by the M3 audit logger)."""

    model_config = ConfigDict(extra="forbid")

    sink: AuditSink = "jsonl"
    path: str | None = None
    postgres_url: str | None = None


class ArgumentSpecSchema(BaseModel):
    """One argument's constraints in a tool's ``args_policy`` (M1 #142).

    Mirrors :class:`agent_tooltrust.engine.argument_policy.ArgumentSpec`:
    ``required``, ``forbid`` substrings, inclusive ``min``/``max`` bounds, and
    an ``allowed`` value allowlist. Any combination may be set; an empty spec
    constrains nothing. ``min``/``max`` are validated as numbers so a
    nonnumeric bound is rejected at load time.
    """

    model_config = ConfigDict(extra="forbid")

    required: bool = False
    forbid: list[str] = Field(default_factory=list)
    min: float | None = None
    max: float | None = None
    allowed: list[str] = Field(default_factory=list)


class ToolSpec(BaseModel):
    """One tool definition in the policy document (M1 #88, F-83).

    ``hidden_for`` marks the tool hidden (not exposed at discovery time) for
    the listed agent classes. Hiding is discovery-time only — enforcement is
    unchanged. Unknown keys are rejected.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, description="Tool name (matches taxonomy)")
    hidden_for: list[str] = Field(
        default_factory=list,
        description="Agent classes that must not see this tool",
    )
    args_policy: dict[str, ArgumentSpecSchema] = Field(
        default_factory=dict,
        description="Per-argument constraints for this tool (M1 #142)",
    )


class PolicyDocument(BaseModel):
    """A validated tooltrust.yaml file.

    ``environments`` / ``data_classes`` / ``risk_weights`` / ``rules`` are
    all optional so an org file may inherit them from the posture default via
    the loader's merge. Empty means "no override here".
    """

    model_config = ConfigDict(extra="forbid")

    version: str = Field(min_length=1, description="Policy version (semver-style)")
    posture: Posture = "balanced"
    environments: dict[str, EnvironmentSpec] = Field(default_factory=dict)
    data_classes: dict[str, DataClassSpec] = Field(default_factory=dict)
    risk_weights: dict[str, float] = Field(
        default_factory=dict,
        description="Per-dimension risk weights. Empty means inherit all from the posture preset.",
    )
    rules: list[RuleSpec] = Field(default_factory=list)
    tools: list[ToolSpec] = Field(
        default_factory=list,
        description="Per-tool definitions: hiding + argument policy",
    )
    escalation: EscalationConfig = Field(default_factory=EscalationConfig)
    audit: AuditConfig = Field(default_factory=AuditConfig)

    @field_validator("risk_weights")
    @classmethod
    def _check_risk_weights(cls, v: dict[str, float]) -> dict[str, float]:
        unknown = set(v) - KNOWN_DIMENSIONS
        if unknown:
            raise ValueError(f"unknown risk_weight dimension(s): {sorted(unknown)}")
        for dim, weight in v.items():
            if not 0.0 <= weight <= 1.0:
                raise ValueError(f"risk weight {dim!r} must be in [0, 1], got {weight}")
        return v


def parse_tooltrust_yaml(text: str) -> PolicyDocument:
    """Parse and validate the contents of a tooltrust.yaml document.

    Raises :class:`pydantic.ValidationError` on schema violations. YAML syntax
    errors surface as :class:`yaml.YAMLError` — the loader (M2.2) captures
    both and re-raises a policy-scoped error with line/column resolution.
    """
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError("tooltrust.yaml must contain a single YAML mapping")
    return PolicyDocument.model_validate(data)
