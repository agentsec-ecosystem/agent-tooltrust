"""Tests for M1.3 — the 5-dimension weighted risk scorer.

Issue #14. Default weights [1.0]*5, aggregate normalized to [0,1], band
mapping, and monotonicity (higher-risk cells score higher).
"""

import pytest

from agent_tooltrust.engine.score import ACTION_VALUES, score
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


class TestActionValues:
    def test_read_is_zero_writes_are_low(self):
        assert ACTION_VALUES["read"] == 0.0
        assert ACTION_VALUES["write"] == pytest.approx(0.3)

    def test_delete_and_grant_are_critical(self):
        assert ACTION_VALUES["delete"] == 1.0
        assert ACTION_VALUES["grant"] == 1.0


class TestScore:
    def test_returns_dimensions_for_all_five(self):
        result = score(_call(), POLICY)
        assert set(result.dimensions) == {
            "tool_category",
            "action_class",
            "environment",
            "data_sensitivity",
            "agent_class",
        }

    def test_aggregate_is_weighted_mean(self):
        # search=0.1, read=0.0, staging=0.1, internal=0.2, release-bot=0.1
        result = score(_call(), POLICY)
        expected = (0.1 + 0.0 + 0.1 + 0.2 + 0.1) / 5
        assert result.aggregate == pytest.approx(expected)

    def test_low_risk_call_in_low_band(self):
        result = score(_call(), POLICY)
        assert result.aggregate < 0.25
        assert result.band == "low"

    def test_prod_write_internal_scores_medium_high(self):
        result = score(
            _call(
                tool="deploy_service",
                tool_category="cloud",
                action_class="write",
                environment="production",
            ),
            POLICY,
        )
        # cloud=0.6, write=0.3, prod=0.7, internal=0.2, agent=0.1
        assert result.aggregate == pytest.approx((0.6 + 0.3 + 0.7 + 0.2 + 0.1) / 5)

    def test_destructive_call_scores_critical(self):
        result = score(
            _call(
                tool="drop_database",
                tool_category="db",
                action_class="delete",
                environment="production",
                data_class="customer_pii",
                agent_id="untrusted-nobody",
            ),
            POLICY,
        )
        # db=0.6, delete=1.0, prod=0.7, customer_pii=1.0, untrusted=0.5
        assert result.aggregate >= 0.75
        assert result.band == "critical"

    def test_unknown_environment_scores_conservatively(self):
        result = score(_call(environment="somewhere_new"), POLICY)
        assert result.dimensions["environment"] == 1.0

    def test_unknown_data_class_scores_conservatively(self):
        result = score(_call(data_class="top_secret"), POLICY)
        assert result.dimensions["data_sensitivity"] == 1.0

    def test_monotonicity_higher_env_higher_score(self):
        staging = score(_call(environment="staging"), POLICY)
        production = score(_call(environment="production"), POLICY)
        assert production.aggregate > staging.aggregate

    def test_monotonicity_higher_action_higher_score(self):
        read = score(_call(action_class="read"), POLICY)
        delete = score(_call(action_class="delete"), POLICY)
        assert delete.aggregate > read.aggregate

    def test_monotonicity_higher_domain_higher_score(self):
        search = score(_call(tool_category="search"), POLICY)
        secrets = score(
            _call(tool="read_secrets", tool_category="secrets", action_class="read"), POLICY
        )
        assert secrets.aggregate > search.aggregate

    def test_monotonicity_higher_agent_higher_score(self):
        trusted = score(_call(agent_id="release-bot"), POLICY)
        unknown = score(_call(agent_id="untrusted-nobody"), POLICY)
        assert unknown.aggregate > trusted.aggregate

    def test_weights_influence_aggregate(self):
        policy = default_policy("balanced")
        policy = _with_weights(
            policy,
            {
                "environment": 0.0,
                "action_class": 0.0,
                "data_sensitivity": 0.0,
                "agent_class": 0.0,
                "tool_category": 1.0,
            },
        )
        # Only tool_category contributes; search = 0.1.
        result = score(_call(action_class="delete", environment="production"), policy)
        assert result.aggregate == pytest.approx(0.1)

    def test_zero_weight_policy_scores_zero_without_zerodivision(self):
        zero = _with_weights(
            POLICY,
            {
                "tool_category": 0.0,
                "action_class": 0.0,
                "environment": 0.0,
                "data_sensitivity": 0.0,
                "agent_class": 0.0,
            },
        )
        result = score(_call(), zero)
        assert result.aggregate == 0.0
        assert result.band == "low"


def _with_weights(policy, weights):
    from dataclasses import replace

    return replace(policy, risk_weights=weights)
