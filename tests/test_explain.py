"""Tests for M1.5 — the explanation engine.

Issue #16. reason_code + template substitution + factor breakdown +
criticality. Every decision carries a machine-readable reason_code, a human
explanation, and a factor list.
"""

from agent_tooltrust.engine.decide import decide
from agent_tooltrust.engine.explain import explain
from agent_tooltrust.engine.score import score
from agent_tooltrust.policy.models import default_policy
from agent_tooltrust.types import NormalizedCall

POLICY = default_policy("balanced")


def _call(**overrides):
    values = {
        "tool": "query_logs",
        "tool_category": "search",
        "action": "read",
        "action_class": "read",
        "environment": "staging",
        "data_class": "internal",
        "agent_id": "release-bot",
        "agent_class": "ci-bot",
    }
    values.update(overrides)
    return NormalizedCall(**values)


def _decide(call):
    return decide(call, POLICY)


class TestExplain:
    def test_allow_decision_complete(self):
        call = _call()
        decision = explain(_decide(call), score(call, POLICY), call, POLICY)

        assert decision.decision == "allow"
        assert decision.criticality == "low"
        assert decision.reason_code == "allow_low_risk"
        assert decision.explanation
        assert decision.escalation_id is None

    def test_audit_decision_complete(self):
        call = _call(
            tool="read_secrets",
            tool_category="secrets",
            action_class="read",
            environment="production",
            data_class="restricted",
        )
        decision = explain(_decide(call), score(call, POLICY), call, POLICY)

        assert decision.decision == "audit"
        assert decision.criticality == "medium"
        assert decision.reason_code == "audit_sensitive_data"
        assert decision.policy_version == "1.0.0"

    def test_escalate_prod_write_sets_escalation_id(self):
        call = _call(
            tool="deploy_service",
            tool_category="cloud",
            action_class="write",
            environment="production",
        )
        decision = explain(_decide(call), score(call, POLICY), call, POLICY)

        assert decision.decision == "escalate"
        assert decision.criticality == "high"
        assert decision.reason_code == "escalate_prod_write"
        assert decision.escalation_id is not None
        assert decision.escalation_id.startswith("esc_")

    def test_non_prod_escalate_uses_generic_code(self):
        call = _call(
            tool="drop_database",
            tool_category="db",
            action_class="delete",
            environment="staging",
            data_class="customer_pii",
            agent_id="untrusted-nobody",
        )
        decision = explain(_decide(call), score(call, POLICY), call, POLICY)

        assert decision.decision == "escalate"
        assert decision.reason_code == "escalate_high_risk"

    def test_deny_decision_complete(self):
        call = _call(
            tool="drop_database",
            tool_category="db",
            action="delete",
            action_class="delete",
            environment="production",
            data_class="customer_pii",
        )
        decision = explain(_decide(call), score(call, POLICY), call, POLICY)

        assert decision.decision == "deny"
        assert decision.criticality == "critical"
        assert decision.reason_code == "deny_critical_op"

    def test_deny_explanation_includes_rule_reason(self):
        call = _call(
            tool="drop_database",
            tool_category="db",
            action="delete",
            action_class="delete",
            environment="production",
            data_class="internal",
        )
        decision = explain(_decide(call), score(call, POLICY), call, POLICY)
        assert "Deletes in production are blocked" in decision.explanation

    def test_explanation_is_parameterized_with_call_context(self):
        call = _call()
        decision = explain(_decide(call), score(call, POLICY), call, POLICY)
        assert call.tool in decision.explanation
        assert call.environment in decision.explanation

    def test_factors_cover_all_dimensions(self):
        call = _call()
        decision = explain(_decide(call), score(call, POLICY), call, POLICY)
        dimensions = {f.dimension for f in decision.factors}
        assert dimensions == {
            "tool_category",
            "action_class",
            "environment",
            "data_sensitivity",
            "agent_class",
        }

    def test_factors_have_human_values(self):
        call = _call(tool="deploy_service", tool_category="cloud", action_class="write")
        decision = explain(_decide(call), score(call, POLICY), call, POLICY)
        by_dim = {f.dimension: f.value for f in decision.factors}
        assert by_dim["tool_category"] == "cloud"
        assert by_dim["action_class"] == "write"
        assert by_dim["environment"] == "staging"
        assert by_dim["data_sensitivity"] == "internal"
        assert by_dim["agent_class"] == "ci-bot"

    def test_factor_contributions_match_dimension_scores(self):
        call = _call()
        rs = score(call, POLICY)
        decision = explain(_decide(call), rs, call, POLICY)
        by_dim = {f.dimension: f.contribution for f in decision.factors}
        assert by_dim == rs.dimensions

    def test_allow_is_dry_run_false(self):
        call = _call()
        decision = explain(_decide(call), score(call, POLICY), call, POLICY)
        assert decision.dry_run is False

    def test_deny_explanation_nonempty_and_actionable(self):
        call = _call(
            tool="drop_database",
            tool_category="db",
            action_class="delete",
            environment="production",
            data_class="internal",
        )
        decision = explain(_decide(call), score(call, POLICY), call, POLICY)
        assert decision.explanation
        assert "staging" in decision.explanation or "read-only" in decision.explanation
