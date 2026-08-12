"""Field test data models — agent roster, scenario matrix, test case results."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ScenarioType = Literal["decision", "adversarial"]

#: Decision fields asserted per (scenario, agent_class) cell.
CELL_FIELDS = ("decision", "criticality", "reason_code")


@dataclass(frozen=True)
class FieldAgent:
    """One agent in the field test roster.

    Attributes:
        agent_id: Unique identity; resolves to an ``agent_class`` in policy.
        framework: The agent framework (langgraph, pydanticai, ...).
        agent_class: Policy agent class the identity maps to.
        domain: Task domain (code-gen, rag, web, ...).
        tools: Tool names the agent would call.
        source: Upstream repo the agent is sourced from.
    """

    agent_id: str
    framework: str
    agent_class: str
    domain: str = ""
    tools: tuple[str, ...] = ()
    source: str = ""


@dataclass(frozen=True)
class FieldScenario:
    """One scenario in the field test matrix.

    Attributes:
        id: Unique scenario id.
        type: ``decision`` (golden matrix) or ``adversarial`` (CUJ 11).
        tool: Raw tool name to evaluate (may contain an attack).
        action: Action verb.
        environment: Deployment environment.
        data_class: Data sensitivity label.
        expected: Mapping of agent_class → expected cell dict. ``"*"`` applies
            to every agent class. A cell has keys ``decision``,
            ``criticality``, ``reason_code``.
    """

    id: str
    type: ScenarioType
    tool: Any
    action: Any
    environment: Any
    data_class: Any
    expected: dict[str, dict[str, str]] = field(default_factory=dict)

    def expected_for(self, agent_class: str) -> dict[str, str] | None:
        """Return the expected cell for an agent class.

        Exact class match wins; the ``"*"`` wildcard is the fallback.

        Args:
            agent_class: The agent's policy class.

        Returns:
            The expected cell dict, or None when nothing applies.
        """
        if agent_class in self.expected:
            return self.expected[agent_class]
        return self.expected.get("*")


@dataclass
class FieldTestCase:
    """Result of evaluating one (agent, scenario) pair.

    Attributes:
        agent: The agent under test.
        scenario: The scenario applied.
        agent_class: Resolved policy class for the agent.
        expected: The expected cell dict applied (may be None if no rule).
        actual: The decision string returned by the engine.
        criticality: The criticality string returned by the engine.
        reason_code: The reason code returned by the engine.
        passed: Whether the actuals matched the expectation.
        notes: Human-readable failure detail.
    """

    agent: FieldAgent
    scenario: FieldScenario
    agent_class: str
    expected: dict[str, str] | None
    actual: str
    criticality: str
    reason_code: str
    passed: bool
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        """JSON-friendly representation of this test case."""
        return {
            "scenario_id": self.scenario.id,
            "scenario_type": self.scenario.type,
            "agent_id": self.agent.agent_id,
            "framework": self.agent.framework,
            "agent_class": self.agent_class,
            "tool": self.scenario.tool,
            "action": self.scenario.action,
            "environment": self.scenario.environment,
            "data_class": self.scenario.data_class,
            "expected": self.expected,
            "actual_decision": self.actual,
            "actual_criticality": self.criticality,
            "actual_reason_code": self.reason_code,
            "passed": self.passed,
            "notes": self.notes,
        }
