"""Tests for M1.8 — the engine facade.

Issue #19. ``Engine.evaluate`` runs the full pipeline (normalize -> score ->
decide -> explain) and returns a complete Decision, failing closed on any
error. A pluggable LLM explainer may enrich the explanation.
"""

import pytest

from agent_tooltrust.engine.engine import Engine
from agent_tooltrust.errors import (
    DENY_MALFORMED_INPUT,
    DENY_UNKNOWN_TOOL,
    ESCALATE_PROD_WRITE,
)
from agent_tooltrust.policy.models import default_policy


@pytest.fixture
def engine():
    return Engine(default_policy("balanced"))


class TestEngine:
    def test_evaluate_returns_complete_decision(self, engine):
        decision = engine.evaluate(
            tool_name="query_logs",
            action="read",
            environment="staging",
            data_class="internal",
            agent_id="release-bot",
        )
        assert decision.decision == "allow"
        assert decision.reason_code == "allow_low_risk"
        assert decision.criticality == "low"
        assert decision.explanation
        assert len(decision.factors) == 5
        assert decision.policy_version == "1.0.0"

    def test_evaluate_denies_unknown_tool_fail_closed(self, engine):
        decision = engine.evaluate(
            tool_name="rm -rf /",
            action="delete",
            environment="production",
            data_class="restricted",
            agent_id="release-bot",
        )
        assert decision.decision == "deny"
        assert decision.reason_code == DENY_UNKNOWN_TOOL

    def test_evaluate_denies_blank_input(self, engine):
        decision = engine.evaluate(
            tool_name="",
            action="read",
            environment="production",
            data_class="restricted",
            agent_id="release-bot",
        )
        assert decision.decision == "deny"
        assert decision.reason_code == DENY_MALFORMED_INPUT

    def test_evaluate_denies_non_string_tool_fail_closed(self, engine):
        decision = engine.evaluate(
            tool_name=None,  # type: ignore[arg-type]
            action="read",
            environment="production",
            data_class="restricted",
            agent_id="release-bot",
        )
        assert decision.decision == "deny"
        assert decision.reason_code == DENY_MALFORMED_INPUT

    def test_evaluate_denies_non_string_environment_fail_closed(self, engine):
        decision = engine.evaluate(
            tool_name="query_logs",
            action="read",
            environment=42,  # type: ignore[arg-type]
            data_class="restricted",
            agent_id="release-bot",
        )
        assert decision.decision == "deny"
        assert decision.reason_code == DENY_MALFORMED_INPUT

    def test_evaluate_resolves_confusable_tool(self, engine):
        decision = engine.evaluate(
            tool_name="query_loɡs",
            action="read",
            environment="staging",
            data_class="internal",
            agent_id="release-bot",
        )
        assert decision.decision == "allow"

    def test_evaluate_escalates_prod_write(self, engine):
        decision = engine.evaluate(
            tool_name="deploy_service",
            action="deploy",
            environment="production",
            data_class="restricted",
            agent_id="dev-eng",
        )
        assert decision.decision == "escalate"
        assert decision.reason_code == ESCALATE_PROD_WRITE
        assert decision.escalation_id is not None

    def test_evaluate_respects_agent_profile(self, engine):
        trusted = engine.evaluate(
            tool_name="drop_database",
            action="delete",
            environment="staging",
            data_class="restricted",
            agent_id="release-bot",
        )
        untrusted = engine.evaluate(
            tool_name="drop_database",
            action="delete",
            environment="staging",
            data_class="restricted",
            agent_id="untrusted-nobody",
        )
        assert trusted.decision == "audit"
        assert untrusted.decision == "escalate"

    def test_arguments_and_context_are_accepted(self, engine):
        decision = engine.evaluate(
            tool_name="query_logs",
            action="read",
            environment="staging",
            data_class="internal",
            agent_id="release-bot",
            arguments={"query": "SELECT 1"},
            context={"user": "svc-2fa"},
        )
        assert decision.decision == "allow"


class TestEngineWithExplainer:
    def test_explainer_can_replace_explanation(self):
        engine = Engine(default_policy("balanced"), explainer=lambda d, c: "LLM said: ok")
        decision = engine.evaluate(
            tool_name="query_logs",
            action="read",
            environment="staging",
            data_class="internal",
            agent_id="release-bot",
        )
        assert decision.explanation == "LLM said: ok"
