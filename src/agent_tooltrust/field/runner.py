"""Field test runner — evaluate the scenario matrix against the engine.

``FieldTestRunner`` loads an agent roster and a scenario matrix, evaluates
every (agent, scenario) pair through a ToolTrust Engine, and asserts the
resulting decision/criticality/reason_code against the golden expectations.

Agents are differentiated by their identity: each ``agent_id`` resolves to an
``agent_class`` in policy, and scenarios carry per-class expectations. The
framework metadata on the agent is recorded for reporting but does not change
engine behavior — the engine is framework-agnostic by design.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

import yaml

from agent_tooltrust.engine.engine import Engine
from agent_tooltrust.field.models import CELL_FIELDS, FieldAgent, FieldScenario, FieldTestCase
from agent_tooltrust.policy.models import AgentProfile, Policy, default_policy

#: Risk per agent class, used to build profiles for the field test policy.
CLASS_RISK: dict[str, float] = {
    "ci-bot": 0.1,
    "engineer": 0.3,
    "general": 0.5,
    "analyst": 0.7,
    "sensitive": 0.9,
}


def default_field_policy(
    posture: str = "balanced",
    agents: Iterable[FieldAgent] = (),
) -> Policy:
    """Build the policy used by the field test harness.

    Registers a profile for every known agent class (with per-class risk) and
    for every roster agent id, so identities resolve to the class their
    expectations are keyed on.

    Args:
        posture: Posture preset (strict/balanced/permissive).
        agents: Optional roster; each agent id is registered with its class's
            risk so ``agent_id`` resolves to the right profile.

    Returns:
        A :class:`Policy` with agent profiles for the field test classes.
    """
    base = default_policy(posture)
    registered: dict[str, AgentProfile] = dict(base.agents)
    for cls, risk in CLASS_RISK.items():
        registered[cls] = AgentProfile(cls, risk)
    for agent in agents:
        risk = CLASS_RISK.get(agent.agent_class, 0.5)
        registered[agent.agent_id] = AgentProfile(agent.agent_class, risk)
    return Policy(
        version=base.version,
        posture=base.posture,
        environments=base.environments,
        data_classes=base.data_classes,
        risk_weights=base.risk_weights,
        rules=base.rules,
        agents=registered,
        default_agent=AgentProfile("general", 0.5),
    )


@dataclass
class FieldTestReport:
    """Aggregate results of a full field test run.

    Attributes:
        cases: Every test case evaluated.
        decision_cases: Cases of type ``decision``.
        adversarial_cases: Cases of type ``adversarial``.
    """

    cases: list[FieldTestCase] = field(default_factory=list)

    @property
    def decision_cases(self) -> list[FieldTestCase]:
        """Return the decision-matrix cases."""
        return [c for c in self.cases if c.scenario.type == "decision"]

    @property
    def adversarial_cases(self) -> list[FieldTestCase]:
        """Return the adversarial-sub-matrix cases."""
        return [c for c in self.cases if c.scenario.type == "adversarial"]

    @property
    def total(self) -> int:
        """Total number of cases evaluated."""
        return len(self.cases)

    @property
    def passed(self) -> int:
        """Number of passing cases."""
        return sum(1 for c in self.cases if c.passed)

    @property
    def failed(self) -> int:
        """Number of failing cases."""
        return self.total - self.passed

    def pass_rate(self, cases: Iterable[FieldTestCase] | None = None) -> float:
        """Compute the pass rate (0.0-1.0) for the given cases.

        Args:
            cases: Cases to measure; defaults to all cases.

        Returns:
            The fraction of cases that passed.
        """
        items = list(cases) if cases is not None else self.cases
        if not items:
            return 0.0
        return sum(1 for c in items if c.passed) / len(items)

    def framework_pass_rates(self) -> dict[str, float]:
        """Compute the pass rate per framework.

        Returns:
            Mapping of framework → pass rate (0.0-1.0).
        """
        by_framework: dict[str, list[FieldTestCase]] = {}
        for case in self.cases:
            by_framework.setdefault(case.agent.framework, []).append(case)
        return {fw: self.pass_rate(items) for fw, items in by_framework.items()}

    def failures(self) -> list[FieldTestCase]:
        """Return the failing cases, for reporting and debugging."""
        return [c for c in self.cases if not c.passed]


class FieldTestRunner:
    """Run the field test scenario matrix against a ToolTrust Engine.

    Args:
        engine: A configured Engine instance (all cases run through it).
        scenarios: Scenario matrix. Defaults to an empty matrix; load via
            :meth:`load_scenarios`.
        agents: Agent roster. Defaults to empty; load via :meth:`load_agents`.
    """

    def __init__(
        self,
        engine: Engine,
        scenarios: Iterable[FieldScenario] = (),
        agents: Iterable[FieldAgent] = (),
    ) -> None:
        self._engine = engine
        self._scenarios = list(scenarios)
        self._agents = list(agents)

    def add_scenario(self, scenario: FieldScenario) -> None:
        """Add a scenario to the matrix.

        Args:
            scenario: The scenario to append.
        """
        self._scenarios.append(scenario)

    def add_agent(self, agent: FieldAgent) -> None:
        """Add an agent to the roster.

        Args:
            agent: The agent to append.
        """
        self._agents.append(agent)

    def load_scenarios(self, path: str) -> None:
        """Load the scenario matrix from a YAML file.

        Args:
            path: Path to the scenarios YAML.
        """
        data = yaml.safe_load(open(path, encoding="utf-8").read())
        scenarios = data.get("scenarios", data) if isinstance(data, dict) else data
        for item in scenarios:
            self._scenarios.append(self._parse_scenario(item))

    def load_agents(self, path: str) -> None:
        """Load the agent roster from a YAML file.

        Args:
            path: Path to the agents YAML.
        """
        data = yaml.safe_load(open(path, encoding="utf-8").read())
        agents = data.get("agents", data) if isinstance(data, dict) else data
        for item in agents:
            self._agents.append(self._parse_agent(item))

    @classmethod
    def from_files(
        cls,
        scenarios_path: str,
        agents_path: str,
        posture: str = "balanced",
    ) -> FieldTestRunner:
        """Build a runner with a policy that knows every roster agent id.

        Loads the roster first, registers each agent id with its class's risk,
        then constructs the engine and builds the runner.

        Args:
            scenarios_path: Path to the scenario matrix YAML.
            agents_path: Path to the agent roster YAML.
            posture: Posture preset for the base policy.

        Returns:
            A ready-to-run :class:`FieldTestRunner`.
        """
        preload = FieldTestRunner(cls._blank_engine())
        preload.load_agents(agents_path)
        policy = default_field_policy(posture, preload._agents)
        runner = FieldTestRunner(Engine(policy))
        runner.load_scenarios(scenarios_path)
        runner.load_agents(agents_path)
        return runner

    @staticmethod
    def _blank_engine() -> Engine:
        return Engine(default_policy("balanced"))

    def run(
        self,
        *,
        agents: Iterable[str] | None = None,
        scenario_types: Iterable[str] | None = None,
    ) -> FieldTestReport:
        """Run every (agent, scenario) pair and return the report.

        Args:
            agents: Optional filter of agent ids to run (default: all).
            scenario_types: Optional filter of scenario types to run
                (``decision``/``adversarial``, default: both).

        Returns:
            A :class:`FieldTestReport` with one case per pair.
        """
        agent_filter = set(agents) if agents is not None else None
        type_filter = set(scenario_types) if scenario_types is not None else None

        report = FieldTestReport()
        for agent in self._agents:
            if agent_filter is not None and agent.agent_id not in agent_filter:
                continue
            for scenario in self._scenarios:
                if type_filter is not None and scenario.type not in type_filter:
                    continue
                report.cases.append(self._run_case(agent, scenario))
        return report

    def _run_case(self, agent: FieldAgent, scenario: FieldScenario) -> FieldTestCase:
        expected = scenario.expected_for(agent.agent_class)
        decision = self._engine.evaluate(
            tool_name=scenario.tool,
            action=scenario.action,
            environment=scenario.environment,
            data_class=scenario.data_class,
            agent_id=agent.agent_id,
        )
        actual = decision.decision
        actual_criticality = decision.criticality
        actual_reason = decision.reason_code

        if expected is None:
            return FieldTestCase(
                agent=agent,
                scenario=scenario,
                agent_class=agent.agent_class,
                expected=expected,
                actual=actual,
                criticality=actual_criticality,
                reason_code=actual_reason,
                passed=False,
                notes="no expectation for this agent class",
            )

        mismatches = [
            field_name
            for field_name in CELL_FIELDS
            if expected.get(field_name) not in (None, getattr(decision, field_name, ""))
        ]
        passed = not mismatches
        notes = ""
        if not passed:
            detail = "; ".join(
                f"{m}: expected {expected[m]!r}, got {getattr(decision, m)!r}" for m in mismatches
            )
            notes = f"mismatch: {detail}"

        return FieldTestCase(
            agent=agent,
            scenario=scenario,
            agent_class=agent.agent_class,
            expected=expected,
            actual=actual,
            criticality=actual_criticality,
            reason_code=actual_reason,
            passed=passed,
            notes=notes,
        )

    @staticmethod
    def _parse_scenario(item: dict[str, Any]) -> FieldScenario:
        expected: dict[str, dict[str, str]] = {}
        for key, value in (item.get("expected") or {}).items():
            expected[str(key)] = {str(k): str(v) for k, v in value.items()}
        return FieldScenario(
            id=str(item["id"]),
            type=str(item.get("type", "decision")),  # type: ignore[arg-type]
            tool=item["tool"],
            action=item["action"],
            environment=item["environment"],
            data_class=item["data_class"],
            expected=expected,
        )

    @staticmethod
    def _parse_agent(item: dict[str, Any]) -> FieldAgent:
        return FieldAgent(
            agent_id=str(item["agent_id"]),
            framework=str(item["framework"]),
            agent_class=str(item.get("agent_class", "general")),
            domain=str(item.get("domain", "")),
            tools=tuple(str(t) for t in item.get("tools", [])),
            source=str(item.get("source", "")),
        )
