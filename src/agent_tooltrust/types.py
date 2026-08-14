"""Core data types for the Agent ToolTrust decision pipeline.

These are strict, frozen dataclasses. Freezing makes the evaluation result
an immutable value that can be safely shared, cached, and audited. Field
validation happens on construction so a malformed call is rejected early
and can never flow into the scorer.
"""

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

DecisionValue = Literal["allow", "audit", "escalate", "deny", "allow_with_obligation"]
Criticality = Literal["none", "low", "medium", "high", "critical"]
ActionClass = Literal["read", "write", "delete", "grant"]
RiskBand = Literal["low", "medium", "high", "critical"]

_VALID_DECISIONS = frozenset(
    {"allow", "audit", "escalate", "deny", "allow_with_obligation"}
)
_VALID_CRITICALITIES = frozenset({"none", "low", "medium", "high", "critical"})
_VALID_ACTION_CLASSES = frozenset({"read", "write", "delete", "grant"})
_VALID_BANDS = frozenset({"low", "medium", "high", "critical"})


def _require_nonblank(value: str, name: str) -> None:
    if not value or not value.strip():
        raise ValueError(f"{name} must be a non-blank string")


@dataclass(frozen=True)
class Factor:
    """A single contributing dimension of a risk score."""

    dimension: str
    value: str
    contribution: float

    def __post_init__(self) -> None:
        _require_nonblank(self.dimension, "dimension")
        if not 0.0 <= self.contribution <= 1.0:
            raise ValueError(f"contribution must be in [0, 1], got {self.contribution}")

    def to_dict(self) -> dict[str, str | float]:
        """JSON-friendly representation of this factor."""
        return {
            "dimension": self.dimension,
            "value": self.value,
            "contribution": self.contribution,
        }


@dataclass(frozen=True)
class NormalizedCall:
    """A canonicalized tool call after the normalize stage.

    All strings are whitespace-collapsed and Unicode NFKC-normalized. The
    ``tool_category`` and ``action_class`` fields are resolved from the
    taxonomy; ``agent_class`` is resolved from policy.
    """

    tool: str
    tool_category: str
    action: str
    action_class: ActionClass
    environment: str
    data_class: str
    agent_id: str
    agent_class: str
    session_id: str | None = None
    arguments: dict[str, Any] | None = None
    context: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "tool",
            "tool_category",
            "action",
            "environment",
            "data_class",
            "agent_id",
            "agent_class",
        ):
            _require_nonblank(getattr(self, field_name), field_name)
        if self.action_class not in _VALID_ACTION_CLASSES:
            raise ValueError(
                f"action_class must be one of {sorted(_VALID_ACTION_CLASSES)}, "
                f"got {self.action_class!r}"
            )

    def to_dict(self) -> dict[str, Any]:
        """JSON-friendly representation of this call."""
        return asdict(self)


@dataclass(frozen=True)
class RiskScore:
    """The 5-dimension risk score produced by the scorer."""

    dimensions: dict[str, float]
    aggregate: float
    band: RiskBand

    def __post_init__(self) -> None:
        for dim, value in self.dimensions.items():
            _require_nonblank(dim, "dimension")
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"dimension {dim!r} out of [0, 1]: {value}")
        if not 0.0 <= self.aggregate <= 1.0:
            raise ValueError(f"aggregate must be in [0, 1], got {self.aggregate}")
        if self.band not in _VALID_BANDS:
            raise ValueError(f"band must be one of {sorted(_VALID_BANDS)}, got {self.band!r}")

    def to_dict(self) -> dict[str, Any]:
        """JSON-friendly representation of this score."""
        return asdict(self)


@dataclass(frozen=True)
class Decision:
    """The final verdict produced by the pipeline for one tool call."""

    decision: DecisionValue
    criticality: Criticality
    reason_code: str
    explanation: str
    factors: list[Factor] = field(default_factory=list)
    escalation_id: str | None = None
    policy_version: str = "0.0.0"
    dry_run: bool = False
    obligations: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.decision not in _VALID_DECISIONS:
            raise ValueError(
                f"decision must be one of {sorted(_VALID_DECISIONS)}, got {self.decision!r}"
            )
        if self.criticality not in _VALID_CRITICALITIES:
            raise ValueError(
                f"criticality must be one of {sorted(_VALID_CRITICALITIES)}, "
                f"got {self.criticality!r}"
            )
        _require_nonblank(self.reason_code, "reason_code")

    def to_dict(self) -> dict[str, Any]:
        """JSON-friendly representation of this decision."""
        return asdict(self)
