"""Tests for M2 Task 2 (#108, F-88) — child-agent delegation.

A child agent's scope must be a subset of its parent's scope
(confused-deputy protection). Subset is allowed; superset is denied; unknown
parent denied. The delegation registry records the parent→child chain so the
audit trail can show who spawned whom.
"""

from __future__ import annotations

from agent_tooltrust.engine.delegation import DelegationManager, DelegationResult
from agent_tooltrust.engine.engine import Engine
from agent_tooltrust.errors import (
    DENY_DELEGATION_EXCEEDS_SCOPE,
    DENY_DELEGATION_UNKNOWN_PARENT,
)
from agent_tooltrust.policy.models import AgentProfile, Policy, default_policy


def _policy(agents=None):
    base = default_policy("balanced")
    merged = dict(base.agents)
    merged.update(agents or {})
    return Policy(
        version=base.version,
        posture=base.posture,
        environments=base.environments,
        data_classes=base.data_classes,
        risk_weights=base.risk_weights,
        rules=base.rules,
        agents=merged,
    )


class TestScopeSubsetInvariant:
    def test_child_subset_of_parent_allowed(self):
        policy = _policy(
            {"parent-bot": AgentProfile("ci-bot", 0.1, environments=("staging", "production"))}
        )
        engine = Engine(policy)
        result = engine.delegate("child-bot", "parent-bot", environments=("staging",))
        assert result.allowed is True
        assert result.reason_code == "allow_delegation"
        assert result.delegation is not None
        assert result.delegation.parent_id == "parent-bot"

    def test_child_equal_scope_to_parent_allowed(self):
        policy = _policy({"parent-bot": AgentProfile("ci-bot", 0.1, environments=("staging",))})
        engine = Engine(policy)
        result = engine.delegate("child-bot", "parent-bot", environments=("staging",))
        assert result.allowed is True

    def test_child_superset_of_parent_denied(self):
        policy = _policy(
            {"parent-bot": AgentProfile("ci-bot", 0.1, environments=("staging", "production"))}
        )
        engine = Engine(policy)
        result = engine.delegate("child-bot", "parent-bot", environments=("staging", "pre_prod"))
        assert result.allowed is False
        assert result.reason_code == DENY_DELEGATION_EXCEEDS_SCOPE
        assert "exceeds parent" in result.explanation

    def test_child_scope_disjoint_from_parent_denied(self):
        policy = _policy({"parent-bot": AgentProfile("ci-bot", 0.1, environments=("staging",))})
        engine = Engine(policy)
        result = engine.delegate("child-bot", "parent-bot", environments=("production",))
        assert result.allowed is False
        assert result.reason_code == DENY_DELEGATION_EXCEEDS_SCOPE

    def test_unrestricted_parent_may_delegate_any_scope(self):
        policy = _policy({"parent-bot": AgentProfile("ci-bot", 0.1)})
        engine = Engine(policy)
        result = engine.delegate("child-bot", "parent-bot", environments=("production",))
        assert result.allowed is True

    def test_unknown_parent_denied(self):
        engine = Engine(default_policy("balanced"))
        result = engine.delegate("child-bot", "no-such-bot", environments=("staging",))
        assert result.allowed is False
        assert result.reason_code == DENY_DELEGATION_UNKNOWN_PARENT

    def test_default_agent_is_not_an_authorized_parent(self):
        engine = Engine(default_policy("balanced"))
        result = engine.delegate("child-bot", "unknown-identity", environments=())
        assert result.allowed is False
        assert result.reason_code == DENY_DELEGATION_UNKNOWN_PARENT


class TestDelegationChain:
    def test_registry_records_delegation(self):
        policy = _policy(
            {"parent-bot": AgentProfile("ci-bot", 0.1, environments=("staging", "production"))}
        )
        engine = Engine(policy)
        engine.delegate("child-bot", "parent-bot", environments=("staging",))
        assert engine.delegation_manager.child_ids_of("parent-bot") == ("child-bot",)

    def test_delegation_chain_parent_lineage(self):
        policy = _policy(
            {
                "root-bot": AgentProfile("ci-bot", 0.1, environments=("staging", "production")),
                "mid-bot": AgentProfile("ci-bot", 0.1, environments=("staging", "production")),
            }
        )
        engine = Engine(policy)
        engine.delegate("mid-bot", "root-bot", environments=("staging", "production"))
        engine.delegate("leaf-bot", "mid-bot", environments=("staging",))
        assert engine.delegation_manager.delegation_chain("leaf-bot") == (
            "leaf-bot",
            "mid-bot",
            "root-bot",
        )

    def test_chain_stops_at_non_delegated_parent(self):
        policy = _policy({"parent-bot": AgentProfile("ci-bot", 0.1, environments=("staging",))})
        engine = Engine(policy)
        engine.delegate("child-bot", "parent-bot", environments=("staging",))
        chain = engine.delegation_manager.delegation_chain("child-bot")
        assert chain == ("child-bot", "parent-bot")

    def test_chain_for_unknown_identity_is_itself(self):
        engine = Engine(default_policy("balanced"))
        assert engine.delegation_manager.delegation_chain("no-one") == ("no-one",)

    def test_delegation_record_carries_environment_scope(self):
        policy = _policy(
            {"parent-bot": AgentProfile("ci-bot", 0.1, environments=("staging", "production"))}
        )
        engine = Engine(policy)
        result = engine.delegate("child-bot", "parent-bot", environments=("production",))
        assert result.delegation is not None
        assert result.delegation.environments == ("production",)
        assert result.delegation.child_id == "child-bot"


def test_manager_works_without_engine():
    manager = DelegationManager()
    policy = _policy(
        {"parent-bot": AgentProfile("ci-bot", 0.1, environments=("staging", "production"))}
    )
    result = manager.delegate("child-bot", "parent-bot", policy, environments=("staging",))
    assert isinstance(result, DelegationResult)
    assert result.allowed is True
    assert manager.delegations["child-bot"].parent_id == "parent-bot"


def test_deny_result_has_no_delegation_record():
    engine = Engine(default_policy("balanced"))
    result = engine.delegate("child-bot", "no-such-parent", environments=("staging",))
    assert result.allowed is False
    assert result.delegation is None
    assert result.reason_code == DENY_DELEGATION_UNKNOWN_PARENT
