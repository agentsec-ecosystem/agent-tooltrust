"""Tests for M2 Task 1 (#145, DD-18) — resource & environment scoping.

A session declares a scope (environments + optional resource tags). The
engine enforces it default-deny: a call resolving outside the scope is denied
before scoring, and the deny is audited. Identities may also carry an
environment allowlist (resource-scoped identity) from the policy profile.
"""

from __future__ import annotations

import pytest

from agent_tooltrust.audit.logger import AuditLogger
from agent_tooltrust.audit.sinks.jsonl import JsonlSink
from agent_tooltrust.engine.engine import Engine
from agent_tooltrust.engine.scoping import SessionScope, scoping_violation
from agent_tooltrust.errors import DENY_OUT_OF_SCOPE
from agent_tooltrust.policy.models import AgentProfile, Policy, default_policy
from agent_tooltrust.types import NormalizedCall


def _call(environment: str = "staging", resource_tag: str | None = None) -> NormalizedCall:
    return NormalizedCall(
        tool="query_logs",
        tool_category="observability",
        action="read",
        action_class="read",
        environment=environment,
        data_class="internal",
        agent_id="debug-bot",
        agent_class="general",
        resource_tag=resource_tag,
    )


class TestSessionScope:
    def test_scope_none_is_unrestricted(self):
        assert scoping_violation(_call("production"), None) is None

    def test_empty_scope_environments_allow_any_environment(self):
        assert scoping_violation(_call("production"), SessionScope()) is None

    def test_in_scope_environment_passes(self):
        assert (
            scoping_violation(_call("staging"), SessionScope(environments=frozenset({"staging"})))
            is None
        )

    def test_out_of_scope_environment_violates(self):
        violation = scoping_violation(
            _call("production"), SessionScope(environments=frozenset({"staging"}))
        )
        assert violation is not None
        assert "outside session scope" in violation

    def test_resource_tag_without_restriction_passes(self):
        scope = SessionScope(environments=frozenset({"staging"}))
        assert scoping_violation(_call("staging", resource_tag="web"), scope) is None

    def test_resource_tag_allowlist_enforced(self):
        scope = SessionScope(resource_tags=("web", "db"))
        assert scoping_violation(_call("staging", resource_tag="web"), scope) is None
        violation = scoping_violation(_call("staging", resource_tag="secret"), scope)
        assert violation is not None
        assert "outside session scope" in violation

    def test_empty_tag_tuple_forbids_all_tagged_resources(self):
        scope = SessionScope(resource_tags=())
        assert scoping_violation(_call("staging", resource_tag="web"), scope) is not None

    def test_scope_allows_blank_environment_rejected(self):
        with pytest.raises(ValueError):
            SessionScope(environments=frozenset({" "}))


class TestEngineScoping:
    def _engine(self, **agents):
        base = default_policy("balanced")
        merged = dict(base.agents)
        merged.update(agents)
        return Engine(
            Policy(
                version=base.version,
                posture=base.posture,
                environments=base.environments,
                data_classes=base.data_classes,
                risk_weights=base.risk_weights,
                rules=base.rules,
                agents=merged,
            )
        )

    def test_prod_entity_rejected_from_staging_session(self):
        engine = self._engine()
        decision = engine.evaluate(
            tool_name="deploy_service",
            action="write",
            environment="production",
            data_class="restricted",
            agent_id="dev-eng",
            session_scope=SessionScope(environments=frozenset({"staging"})),
        )
        assert decision.decision == "deny"
        assert decision.reason_code == DENY_OUT_OF_SCOPE

    def test_in_scope_session_call_allowed(self):
        engine = self._engine()
        decision = engine.evaluate(
            tool_name="query_logs",
            action="read",
            environment="staging",
            data_class="internal",
            agent_id="release-bot",
            session_scope=SessionScope(environments=frozenset({"staging"})),
        )
        assert decision.decision == "allow"

    def test_scope_deny_is_audited(self, tmp_path):
        sink = JsonlSink(str(tmp_path / "audit.jsonl"))
        engine = Engine(default_policy("balanced"), audit_logger=AuditLogger(sink))
        engine.evaluate(
            tool_name="deploy_service",
            action="write",
            environment="production",
            data_class="restricted",
            agent_id="dev-eng",
            session_scope=SessionScope(environments=frozenset({"staging"})),
        )
        entries = sink.query()
        assert len(entries) == 1
        assert entries[0].decision == "deny"
        assert entries[0].reason_code == DENY_OUT_OF_SCOPE

    def test_scope_deny_respects_dry_run(self, tmp_path):
        sink = JsonlSink(str(tmp_path / "audit.jsonl"))
        engine = Engine(
            default_policy("balanced"),
            dry_run=True,
            audit_logger=AuditLogger(sink),
        )
        decision = engine.evaluate(
            tool_name="deploy_service",
            action="write",
            environment="production",
            data_class="restricted",
            agent_id="dev-eng",
            session_scope=SessionScope(environments=frozenset({"staging"})),
        )
        assert decision.decision == "allow"
        assert decision.dry_run is True
        entries = sink.query()
        assert entries[0].decision == "deny"
        assert entries[0].reason_code == DENY_OUT_OF_SCOPE

    def test_resource_tag_violation_denied(self):
        engine = self._engine()
        decision = engine.evaluate(
            tool_name="query_logs",
            action="read",
            environment="staging",
            data_class="internal",
            agent_id="release-bot",
            session_scope=SessionScope(resource_tags=("web",)),
            resource_tag="secret",
        )
        assert decision.decision == "deny"
        assert decision.reason_code == DENY_OUT_OF_SCOPE


class TestIdentityScoping:
    def test_identity_scoped_to_environment(self):
        engine = Engine(
            _policy_with_identity_scope(
                {"prod-bot": AgentProfile("ci-bot", 0.1, environments=("production",))}
            )
        )
        denied = engine.evaluate(
            tool_name="query_logs",
            action="read",
            environment="staging",
            data_class="internal",
            agent_id="prod-bot",
        )
        assert denied.decision == "deny"
        assert denied.reason_code == DENY_OUT_OF_SCOPE
        allowed = engine.evaluate(
            tool_name="query_logs",
            action="read",
            environment="production",
            data_class="internal",
            agent_id="prod-bot",
        )
        assert allowed.decision == "allow"

    def test_unscoped_identity_unrestricted(self):
        engine = Engine(default_policy("balanced"))
        decision = engine.evaluate(
            tool_name="query_logs",
            action="read",
            environment="production",
            data_class="internal",
            agent_id="release-bot",
        )
        assert decision.decision == "allow"

    def test_session_scope_applies_on_top_of_identity_scope(self):
        engine = Engine(
            _policy_with_identity_scope(
                {"prod-bot": AgentProfile("ci-bot", 0.1, environments=("production",))}
            )
        )
        decision = engine.evaluate(
            tool_name="query_logs",
            action="read",
            environment="production",
            data_class="internal",
            agent_id="prod-bot",
            session_scope=SessionScope(environments=frozenset({"staging"})),
        )
        assert decision.decision == "deny"
        assert decision.reason_code == DENY_OUT_OF_SCOPE


def _policy_with_identity_scope(agents):
    base = default_policy("balanced")
    merged = dict(base.agents)
    merged.update(agents)
    return Policy(
        version=base.version,
        posture=base.posture,
        environments=base.environments,
        data_classes=base.data_classes,
        risk_weights=base.risk_weights,
        rules=base.rules,
        agents=merged,
    )
