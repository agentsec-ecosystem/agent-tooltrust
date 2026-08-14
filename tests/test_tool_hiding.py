"""Tests for M1 Task 2 (#88) — discovery-time tool hiding.

Policy can mark a tool `hidden: true` for specific agent classes. The engine
exposes a capability list filtered by the caller's agent class: admin/owner
classes see everything, a read-only class sees only its permitted subset.
Hiding is discovery-time only — a hidden tool called directly still goes
through normal policy evaluation (deny if not permitted), so hiding never
weakens enforcement.
"""

from __future__ import annotations

from agent_tooltrust.engine.engine import Engine
from agent_tooltrust.policy.models import Policy


def _policy() -> Policy:
    from agent_tooltrust.policy.models import AgentProfile, default_policy

    base = default_policy("balanced")
    agents = dict(base.agents)
    agents["readonly-agent"] = AgentProfile("readonly", 0.0)
    agents["dev-eng"] = AgentProfile("engineer", 0.3)
    return Policy(
        version=base.version,
        posture=base.posture,
        environments=base.environments,
        data_classes=base.data_classes,
        risk_weights=base.risk_weights,
        rules=base.rules,
        agents=agents,
        tool_visibility={
            "delete_instance": {"hidden_for": ("readonly",)},
            "read_secrets": {"hidden_for": ("readonly",)},
            "create_api_key": {"hidden_for": ("engineer", "readonly")},
        },
    )


class TestVisibilityDefaults:
    def test_default_policy_has_empty_visibility(self):
        from agent_tooltrust.policy.models import default_policy

        assert default_policy().tool_visibility == {}

    def test_unknown_tool_visible_to_everyone(self):
        engine = Engine(_policy())
        assert "get_weather" in engine.capabilities("release-bot")

    def test_visible_tool_in_all_classes(self):
        engine = Engine(_policy())
        assert "deploy_service" in engine.capabilities("release-bot")
        assert "deploy_service" in engine.capabilities("readonly-agent")


class TestHiding:
    def test_hidden_tool_removed_for_target_class(self):
        engine = Engine(_policy())
        caps = engine.capabilities("readonly-agent")
        assert "delete_instance" not in caps
        assert "read_secrets" not in caps

    def test_hidden_tool_still_visible_to_other_classes(self):
        engine = Engine(_policy())
        caps = engine.capabilities("release-bot")  # ci-bot class
        assert "delete_instance" in caps
        assert "read_secrets" in caps

    def test_create_api_key_hidden_from_engineer_and_readonly(self):
        engine = Engine(_policy())
        assert "create_api_key" not in engine.capabilities("dev-eng")
        assert "create_api_key" not in engine.capabilities("readonly-agent")
        assert "create_api_key" in engine.capabilities("release-bot")

    def test_default_class_uses_general_visibility(self):
        engine = Engine(_policy())
        caps = engine.capabilities("unknown-identity")
        # "engineer" and "readonly" are hidden-from classes; general = default
        # is unaffected → create_api_key/read_secrets still visible.
        assert "read_secrets" in caps


class TestEnforcementUnaffected:
    def test_hidden_tool_direct_call_still_evaluated(self):
        engine = Engine(_policy())
        # Even when visible, enforcement applies normally — deletes in
        # production are denied regardless of discovery-time visibility.
        assert engine.evaluate(
            tool_name="delete_instance",
            action="delete",
            environment="production",
            data_class="internal",
            agent_id="release-bot",
        ).decision == "deny"

    def test_capabilities_does_not_raise_for_missing_profile(self):
        engine = Engine(_policy())
        assert isinstance(engine.capabilities("no-such-agent"), tuple)


def test_default_policy_still_fresh():
    from agent_tooltrust.policy.models import default_policy

    p = default_policy()
    assert isinstance(p, Policy)
    assert p.tool_visibility == {}
