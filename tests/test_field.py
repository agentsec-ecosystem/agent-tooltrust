"""Field harness tests — runner, report, replan, roster, and agent shims.

The deterministic decision/adversarial matrices need no framework packages.
The build_agent shim tests exercise real framework construction and are
skipped when the framework package is not installed (CI-safe).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from agent_tooltrust.engine.engine import Engine
from agent_tooltrust.field.runner import FieldTestRunner, default_field_policy


def _runner(agents: list[dict] | None = None) -> FieldTestRunner:
    from agent_tooltrust.field.models import FieldAgent

    roster = agents or yaml.safe_load(
        Path("tests/field/agents.yaml").read_text(encoding="utf-8")
    )["agents"]
    field_agents = [
        FieldAgent(
            agent_id=a["agent_id"],
            framework=a["framework"],
            agent_class=a["agent_class"],
            domain=a.get("domain", ""),
            tools=tuple(a.get("tools", [])),
            source=a.get("source", ""),
        )
        for a in roster
    ]
    policy = default_field_policy("balanced", field_agents)
    runner = FieldTestRunner(Engine(policy))
    runner.load_scenarios("tests/field/scenarios.yaml")
    for a in field_agents:
        runner.add_agent(a)
    return runner


class TestRoster:
    def test_roster_has_5_to_10_per_framework(self):
        from tests.field.agents.build import load_roster

        by_framework: dict[str, int] = {}
        for a in load_roster():
            by_framework[a["framework"]] = by_framework.get(a["framework"], 0) + 1
        assert len(by_framework) == 10
        for framework, count in by_framework.items():
            assert 5 <= count <= 10, f"{framework} has {count} agents"

    def test_roster_agent_ids_unique(self):
        from tests.field.agents.build import load_roster

        ids = [a["agent_id"] for a in load_roster()]
        assert len(ids) == len(set(ids))

    def test_roster_sources_resolve_when_vendored(self):
        # Vendor checkouts are gitignored and fetched locally by
        # scripts/download_field_agents.sh; CI never checks them out. Only
        # meaningful when the checkout is present on disk.
        vendor_root = Path("tests/field/agents/vendor")
        if not vendor_root.exists():
            pytest.skip("vendor checkout not present (download_field_agents.sh)")
        from tests.field.agents.build import assert_sources_resolve

        unresolved = assert_sources_resolve()
        assert unresolved == [], f"unresolved sources: {unresolved}"


class TestFullMatrix:
    def test_decision_matrix_green(self):
        report = _runner().run(scenario_types=["decision"])
        assert report.failed == 0
        assert len(report.decision_cases) > 0

    def test_adversarial_matrix_green(self):
        report = _runner().run(scenario_types=["adversarial"])
        assert report.failed == 0
        assert len(report.adversarial_cases) > 0

    def test_full_matrix_counts(self):
        report = _runner().run()
        assert report.passed == report.total
        num_agents = len(
            yaml.safe_load(Path("tests/field/agents.yaml").read_text(encoding="utf-8"))["agents"]
        )
        num_scenarios = len(
            yaml.safe_load(Path("tests/field/scenarios.yaml").read_text(encoding="utf-8"))["scenarios"]
        )
        assert report.total == num_agents * num_scenarios

    def test_report_builds_markdown(self):
        from agent_tooltrust.field.report import build_report

        md = build_report(_runner().run())
        assert md.startswith("# Field Test Report")
        assert "Scenario Matrix" in md


class TestReplanScripted:
    def test_scripted_replan_allow_after_deny(self):
        from agent_tooltrust.audit.logger import AuditLogger
        from agent_tooltrust.field.replan import ScriptedReplan

        logger = AuditLogger()
        engine = Engine(default_field_policy("balanced"), audit_logger=logger)
        replan = ScriptedReplan(engine, logger)
        result = replan.run(
            scenario_id="replan-01",
            agent_id="lg-01",
            blocked={
                "tool": "drop_database",
                "action": "delete",
                "environment": "production",
                "data_class": "customer_pii",
            },
            replacement={
                "tool": "query_logs",
                "action": "read",
                "environment": "staging",
                "data_class": "internal",
            },
        )
        assert result.denied == "deny"
        assert result.replacement == "allow"
        assert result.passed


class TestAgentShims:
    """Real build_agent shims — skipped when the framework isn't installed."""

    def test_build_registry_resolves_all_agents(self):
        from tests.field.agents.build import builder_for, load_roster

        for agent in load_roster():
            builder_for(agent["agent_id"])

    def test_scenario_bound_tools_preserve_nonstring_action(self):
        """Guard must receive scenario fields raw, not str()-coerced.

        The ``adversarial-nonstring-08`` scenario declares ``action: 12345``
        (an int) so the engine fails closed with ``deny_malformed_input``.
        Coercing to ``"12345"`` would make it a valid low-risk verb instead.
        """
        from pytest import raises

        from agent_tooltrust.adapters.raw import ToolTrustDecisionError
        from tests.field.agents import scenario_bound_tools

        engine = Engine(default_field_policy("balanced"))
        scenario = {
            "id": "adversarial-nonstring-08",
            "tool": "query_logs",
            "action": 12345,
            "environment": "development",
            "data_class": "public",
        }
        entry = scenario_bound_tools(engine, [scenario], "lg-01")[0]
        with raises(ToolTrustDecisionError) as excinfo:
            entry["fn"](text="x")
        decision = excinfo.value.decision
        assert decision.decision == "deny"
        assert decision.reason_code == "deny_malformed_input"

    def test_tooltrust_mcp_api(self):
        from tests.field.agents import tooltrust_mcp

        agent = tooltrust_mcp.build_agent("mcp-01")
        call = {
            "tool": "query_logs",
            "action": "read",
            "environment": "staging",
            "data_class": "internal",
        }
        decision = agent.evaluate(call)
        assert decision.decision in ("allow", "audit")

    def test_swebench_api(self):
        from tests.field.agents import swebench

        assert swebench.build_agent("swe-01") is not None


class TestReplanSweepScripted:
    """Replan sweep, scripted (deterministic, engine-only — no LLM/framework)."""

    def test_sweep_scripted_all_llm_frameworks_pass(self):
        from agent_tooltrust.field.replan import REPLAN_FRAMEWORKS, run_replan_sweep

        sweep = run_replan_sweep(live=False)
        assert sweep.total == len(REPLAN_FRAMEWORKS)
        assert sweep.total > 0
        assert sweep.passed == sweep.total
        for result in sweep.results:
            assert result.denied == "deny", f"{result.agent_id}: {result.notes}"
            assert result.replacement in ("allow", "audit")
            assert result.passed, f"{result.agent_id}: {result.notes}"

    def test_sweep_live_without_llm_reports_failure(self):
        """Live replan with an unreachable endpoint must fail-closed: each
        result is non-passing with the cause in notes (never a crash/skip)."""
        from agent_tooltrust.field.replan import REPLAN_FRAMEWORKS, run_replan_sweep

        sweep = run_replan_sweep(
            live=True,
            endpoint="http://127.0.0.1:9/v1",  # nothing listens here
        )
        assert sweep.total == len(REPLAN_FRAMEWORKS)
        assert sweep.passed == 0
        assert all("model call failed" in r.notes for r in sweep.results)


@pytest.mark.field
def test_installed_frameworks_build_agents():
    """Build a real agent for every roster id — must not skip.

    The field test is a release gate: if a framework package is missing or a
    build_agent shim raises, the run FAILS so the missing dependency is
    surfaced instead of silently skipped.
    """
    from tests.field.agents import build as registry

    failures: list[str] = []
    for agent in registry.load_roster():
        try:
            agent_obj = registry.build_agent(agent["agent_id"])
            assert agent_obj is not None
        except Exception as exc:
            failures.append(
                f"{agent['agent_id']} ({agent['framework']}): {type(exc).__name__}: {exc}"
            )

    assert not failures, "field test agent build failures:\n" + "\n".join(failures)
