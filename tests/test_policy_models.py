"""Tests for the minimal in-memory policy model used by M1 (scorer/decider).

The full YAML schema + loader + posture presets ship in M2; M1 only needs a
frozen Policy/Rule holder plus the balanced default posture.
"""

from dataclasses import FrozenInstanceError

import pytest

from agent_tooltrust.policy.models import AgentProfile, Rule, default_policy
from agent_tooltrust.types import NormalizedCall


def _call(**overrides):
    values = {
        "tool": "deploy_service",
        "tool_category": "cloud",
        "action": "write",
        "action_class": "write",
        "environment": "production",
        "data_class": "internal",
        "agent_id": "release-bot",
        "agent_class": "ci-bot",
    }
    values.update(overrides)
    return NormalizedCall(**values)


class TestRule:
    def test_defaults_to_wildcards(self):
        rule = Rule(decision="deny")
        assert rule.tool == "*"
        assert rule.action == "*"
        assert rule.environment == "*"
        assert rule.data_class == "*"

    def test_is_frozen(self):
        rule = Rule(decision="deny")
        with pytest.raises(FrozenInstanceError):
            rule.tool = "write_file"  # type: ignore[misc]

    def test_matches_by_tool(self):
        rule = Rule(tool="deploy_service", decision="deny")
        assert rule.matches(_call())
        assert not rule.matches(_call(tool="query_logs", tool_category="search"))

    def test_matches_by_action_name_or_class(self):
        rule = Rule(action="delete", decision="deny")
        # action == "delete" matches directly
        assert rule.matches(_call(action="delete", action_class="delete"))
        # action == "drop" but class == "delete": matches via class
        assert rule.matches(_call(action="drop", action_class="delete"))
        # read action does not match
        assert not rule.matches(_call(action="read", action_class="read"))

    def test_matches_by_environment_and_data_class(self):
        rule = Rule(environment="production", data_class="customer_pii", decision="deny")
        assert rule.matches(_call(data_class="customer_pii"))
        assert not rule.matches(_call(data_class="internal"))

    def test_wildcard_matches_everything(self):
        rule = Rule(decision="deny")
        assert rule.matches(_call(tool="anything", action="whatever"))


class TestPolicy:
    def test_is_frozen(self):
        policy = default_policy()
        with pytest.raises(FrozenInstanceError):
            policy.version = "2.0"  # type: ignore[misc]

    def test_balanced_is_default(self):
        policy = default_policy()
        assert policy.posture == "balanced"

    def test_all_three_postures_exist(self):
        for posture in ("strict", "balanced", "permissive"):
            p = default_policy(posture)
            assert p.posture == posture
            assert p.environments
            assert p.data_classes
            assert p.rules

    def test_risk_weights_default_to_1(self):
        policy = default_policy()
        assert policy.risk_weights == {
            "tool_category": 1.0,
            "action_class": 1.0,
            "environment": 1.0,
            "data_sensitivity": 1.0,
            "agent_class": 1.0,
        }

    def test_version_present(self):
        assert default_policy().version == "1.0.0"

    def test_agent_profile_known(self):
        policy = default_policy()
        profile = policy.agent_profile("release-bot")
        assert isinstance(profile, AgentProfile)
        assert profile.agent_class == "ci-bot"

    def test_agent_profile_unknown_defaults(self):
        policy = default_policy()
        profile = policy.agent_profile("mystery_agent")
        assert profile.agent_class == "general"
        assert profile.risk == pytest.approx(0.5)

    def test_balanced_default_rules_cover_demo_decisions(self):
        policy = default_policy()
        deny_delete_prod = any(
            r.environment == "production" and r.action == "delete" and r.decision == "deny"
            for r in policy.rules
        )
        escalate_write_prod = any(
            r.environment == "production" and r.action == "write" and r.decision == "escalate"
            for r in policy.rules
        )
        deny_grant = any(r.action == "grant" and r.decision == "deny" for r in policy.rules)
        assert deny_delete_prod
        assert escalate_write_prod
        assert deny_grant
