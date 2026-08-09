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
from pydantic import BaseModel, ConfigDict, Field, field_validator

Posture = Literal["strict", "balanced", "permissive"]
RuleDecision = Literal["allow", "audit", "escalate", "deny"]
AuditSink = Literal["jsonl", "sqlite", "postgres"]

#: The five scored dimensions. risk_weights keys are restricted to these so a
#: typo like ``tool_categry`` is caught at load time instead of silently
#: contributing nothing to the aggregate (score() iterates these exact names).
KNOWN_DIMENSIONS = frozenset(
    {"tool_category", "action_class", "environment", "data_sensitivity", "agent_class"}
)


def _in_unit(value: float, mode: str) -> float:
    """Raise ValueError unless *value* is in the [0, 1] risk range."""
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


class RuleSpec(BaseModel):
    """One declarative rule. ``"*"`` means "match anything".

    Field names match the in-memory :class:`Rule` and the architecture §5.4
    example. ``decision`` accepts all four decisions; note the decide stage
    only *enforces* deny > allow > escalate rules and produces ``audit`` from
    the risk band, but org files may still carry an ``audit`` rule for
    documentation/forward-compat.
    """

    model_config = ConfigDict(extra="forbid")

    decision: RuleDecision
    tool: str = "*"
    action: str = "*"
    environment: str = "*"
    data_class: str = "*"
    reason: str = ""


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
        default_factory=lambda: {dim: 1.0 for dim in sorted(KNOWN_DIMENSIONS)}
    )
    rules: list[RuleSpec] = Field(default_factory=list)
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
