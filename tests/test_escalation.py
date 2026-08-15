"""Tests for M3 Task 1 (#84, F-09/F-90) — the EscalationManager.

Covers the escalation round-trip: create a pending escalation bound to an
action identity + TTL; approve -> execute; deny -> agent gets deny; TTL
expiry treated as deny; and the replay/action-identity safety net.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from agent_tooltrust.engine.escalation import (
    EscalationManager,
    EscalationStatus,
    action_identity,
)
from agent_tooltrust.types import NormalizedCall


def _call(
    *,
    tool: str = "deploy_service",
    action: str = "deploy",
    environment: str = "production",
    data_class: str = "restricted",
    agent_id: str = "dev-eng",
    arguments: dict | None = None,
) -> NormalizedCall:
    return NormalizedCall(
        tool=tool,
        tool_category="cloud",
        action=action,
        action_class="write",
        environment=environment,
        data_class=data_class,
        agent_id=agent_id,
        agent_class="engineer",
        arguments=arguments,
    )


def _now() -> datetime:
    return datetime(2026, 8, 13, 12, 0, 0, tzinfo=UTC)


class TestActionIdentity:
    def test_same_call_same_hash(self):
        a = action_identity("git_push", "force_push", {"ref": "main"})
        b = action_identity("git_push", "force_push", {"ref": "main"})
        assert a == b

    def test_different_args_different_hash(self):
        a = action_identity("git_push", "force_push", {"ref": "main"})
        b = action_identity("git_push", "force_push", {"ref": "other"})
        assert a != b

    def test_arg_order_does_not_change_hash(self):
        a = action_identity("deploy_service", "deploy", {"env": "prod", "ver": "2"})
        b = action_identity("deploy_service", "deploy", {"ver": "2", "env": "prod"})
        assert a == b

    def test_none_and_empty_args_hash_differ_from_populated(self):
        assert action_identity("t", "a", None) != action_identity("t", "a", {})


class TestCreate:
    def test_create_makes_pending_escalation(self):
        mgr = EscalationManager(ttl_seconds=300)
        esc = mgr.create(_call(), reason="requires approval")
        assert esc.status == EscalationStatus.PENDING
        assert esc.escalation_id.startswith("esc_")
        assert esc.reason == "requires approval"

    def test_create_binds_action_identity(self):
        mgr = EscalationManager()
        esc = mgr.create(_call(tool="git_push", action="force_push", arguments={"ref": "main"}))
        assert esc.action_identity == action_identity("git_push", "force_push", {"ref": "main"})

    def test_create_sets_ttl(self):
        mgr = EscalationManager(ttl_seconds=300)
        now = _now()
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("agent_tooltrust.engine.escalation._utcnow", lambda: now)
            esc = mgr.create(_call(), now=now)
        assert esc.created_at == now.isoformat()
        assert esc.expires_at == (now + timedelta(seconds=300)).isoformat()

    def test_pending_lists_only_pending(self):
        mgr = EscalationManager()
        mgr.create(_call(agent_id="a"))
        mgr.create(_call(agent_id="b"))
        assert len(mgr.pending()) == 2


class TestApproveDeny:
    def test_approve_executes(self):
        mgr = EscalationManager()
        esc = mgr.create(_call())
        approved = mgr.approve(esc.escalation_id, approver="human@example.com")
        assert approved.status == EscalationStatus.APPROVED
        assert approved.approver == "human@example.com"

    def test_deny_blocks_with_reason(self):
        mgr = EscalationManager()
        esc = mgr.create(_call())
        denied = mgr.deny(esc.escalation_id, approver="human@example.com", reason="not now")
        assert denied.status == EscalationStatus.DENIED
        assert denied.denied_reason == "not now"
        assert denied.approver == "human@example.com"

    def test_approve_unknown_id_raises(self):
        mgr = EscalationManager()
        with pytest.raises(ValueError):
            mgr.approve("esc_nope", approver="human")

    def test_approve_twice_raises(self):
        mgr = EscalationManager()
        esc = mgr.create(_call())
        mgr.approve(esc.escalation_id, approver="human")
        with pytest.raises(ValueError):
            mgr.approve(esc.escalation_id, approver="human")

    def test_blank_approver_rejected(self):
        mgr = EscalationManager()
        esc = mgr.create(_call())
        with pytest.raises(ValueError):
            mgr.approve(esc.escalation_id, approver="  ")


class TestTTLExpiry:
    def test_expired_escalation_is_expired(self):
        mgr = EscalationManager(ttl_seconds=300)
        now = _now()
        esc = mgr.create(_call(), now=now)
        assert esc.is_expired(now + timedelta(seconds=301)) is True
        assert esc.is_expired(now + timedelta(seconds=100)) is False

    def test_approve_expired_raises(self):
        mgr = EscalationManager(ttl_seconds=300)
        now = _now()
        esc = mgr.create(_call(), now=now)
        with pytest.raises(ValueError):
            mgr.approve(esc.escalation_id, approver="human", now=now + timedelta(seconds=301))

    def test_expired_record_marked_expired_after_attempt(self):
        mgr = EscalationManager(ttl_seconds=300)
        now = _now()
        esc = mgr.create(_call(), now=now)
        try:
            mgr.approve(esc.escalation_id, approver="human", now=now + timedelta(seconds=999))
        except ValueError:
            pass
        assert mgr.records[esc.escalation_id].status == EscalationStatus.EXPIRED


class TestResolve:
    def test_resolve_approved_allows(self):
        mgr = EscalationManager()
        call = _call()
        esc = mgr.create(call)
        mgr.approve(esc.escalation_id, approver="human")
        outcome = mgr.resolve(esc.escalation_id, call=call)
        assert outcome["status"] == "allow"
        assert outcome["reason_code"] == "allow_escalation_approved"

    def test_resolve_denied_blocks(self):
        mgr = EscalationManager()
        call = _call()
        esc = mgr.create(call)
        mgr.deny(esc.escalation_id, approver="human", reason="blocked")
        outcome = mgr.resolve(esc.escalation_id, call=call)
        assert outcome["status"] == "deny"
        assert outcome["reason_code"] == "deny_escalation_denied"

    def test_resolve_action_identity_mismatch(self):
        mgr = EscalationManager()
        esc = mgr.create(_call(tool="git_push", action="force_push", arguments={"ref": "main"}))
        mgr.approve(esc.escalation_id, approver="human")
        outcome = mgr.resolve(
            esc.escalation_id,
            call=_call(tool="git_push", action="force_push", arguments={"ref": "other"}),
        )
        assert outcome["status"] == "deny"
        assert outcome["reason_code"] == "deny_action_identity_mismatch"

    def test_resolve_unknown_id_denies(self):
        mgr = EscalationManager()
        outcome = mgr.resolve("esc_nope", call=_call())
        assert outcome["status"] == "deny"
        assert outcome["reason_code"] == "deny_escalation_unknown"

    def test_resolve_expired_denies(self):
        mgr = EscalationManager(ttl_seconds=300)
        now = _now()
        call = _call()
        esc = mgr.create(call, now=now)
        outcome = mgr.resolve(esc.escalation_id, call=call, now=now + timedelta(seconds=999))
        assert outcome["status"] == "deny"
        assert outcome["reason_code"] == "deny_escalation_expired"

    def test_resolve_pending_denies_replay(self):
        mgr = EscalationManager()
        call = _call()
        esc = mgr.create(call)
        outcome = mgr.resolve(esc.escalation_id, call=call)
        assert outcome["status"] == "deny"
        assert outcome["reason_code"] == "deny_escalation_replay"


class TestIdentityIndex:
    def test_find_by_action_identity(self):
        mgr = EscalationManager()
        call = _call()
        esc = mgr.create(call)
        mgr.approve(esc.escalation_id, approver="human")
        assert mgr.find_by_action_identity(esc.action_identity) == esc.escalation_id


class TestSerialization:
    def test_to_dict_shape(self):
        mgr = EscalationManager()
        esc = mgr.create(_call())
        data = esc.to_dict()
        for key in ("escalation_id", "status", "tool", "action", "action_identity", "expired"):
            assert key in data
        assert data["status"] == "pending"


class TestAttest:
    def test_attest_matching_call_returns_record(self):
        mgr = EscalationManager()
        esc = mgr.create(_call())
        assert mgr.attest(esc.escalation_id, call=_call()) == esc

    def test_attest_unknown_id_raises(self):
        mgr = EscalationManager()
        with pytest.raises(ValueError):
            mgr.attest("esc_nope", call=_call())

    def test_attest_already_resolved_raises(self):
        mgr = EscalationManager()
        esc = mgr.create(_call())
        mgr.approve(esc.escalation_id, approver="h")
        with pytest.raises(ValueError):
            mgr.attest(esc.escalation_id, call=_call())

    def test_attest_action_mismatch_raises(self):
        mgr = EscalationManager()
        esc = mgr.create(_call(tool="git_push", arguments={"ref": "main"}))
        with pytest.raises(ValueError):
            mgr.attest(esc.escalation_id, call=_call(tool="git_push", arguments={"ref": "other"}))

    def test_attest_expired_raises_and_marks_expired(self):
        mgr = EscalationManager(ttl_seconds=300)
        now = _now()
        esc = mgr.create(_call(), now=now)
        with pytest.raises(ValueError):
            mgr.attest(esc.escalation_id, call=_call(), now=now + timedelta(seconds=999))
        assert mgr.records[esc.escalation_id].status == EscalationStatus.EXPIRED


class TestDenyErrorPaths:
    def test_deny_unknown_id_raises(self):
        mgr = EscalationManager()
        with pytest.raises(ValueError):
            mgr.deny("esc_nope", approver="h")

    def test_deny_already_resolved_raises(self):
        mgr = EscalationManager()
        esc = mgr.create(_call())
        mgr.deny(esc.escalation_id, approver="h")
        with pytest.raises(ValueError):
            mgr.deny(esc.escalation_id, approver="h")

    def test_deny_expired_raises(self):
        mgr = EscalationManager(ttl_seconds=300)
        now = _now()
        esc = mgr.create(_call(), now=now)
        with pytest.raises(ValueError):
            mgr.deny(esc.escalation_id, approver="h", now=now + timedelta(seconds=999))

    def test_deny_blank_approver_rejected(self):
        mgr = EscalationManager()
        esc = mgr.create(_call())
        with pytest.raises(ValueError):
            mgr.deny(esc.escalation_id, approver=" ")


class TestEngineIntegration:
    def _engine(self):
        from agent_tooltrust.engine.engine import Engine
        from agent_tooltrust.policy.models import default_policy

        return Engine(default_policy("balanced"))

    def test_escalate_decision_registers_escalation(self):
        engine = self._engine()
        decision = engine.evaluate(
            tool_name="deploy_service",
            action="deploy",
            environment="production",
            data_class="restricted",
            agent_id="dev-eng",
        )
        assert decision.decision == "escalate"
        assert decision.escalation_id is not None
        assert decision.escalation_id in engine.escalation_manager.records
        record = engine.escalation_manager.records[decision.escalation_id]
        assert record.tool == "deploy_service"
        assert record.action == "deploy"
        assert record.environment == "production"

    def test_escalation_approve_then_resolve_executes(self):
        engine = self._engine()
        decision = engine.evaluate(
            tool_name="deploy_service",
            action="deploy",
            environment="production",
            data_class="restricted",
            agent_id="dev-eng",
        )
        assert decision.escalation_id is not None
        esc_id = decision.escalation_id
        engine.escalation_manager.approve(esc_id, approver="human@example.com")
        call = _call(
            tool="deploy_service",
            action="deploy",
            environment="production",
            data_class="restricted",
            agent_id="dev-eng",
        )
        outcome = engine.escalation_manager.resolve(esc_id, call=call)
        assert outcome["status"] == "allow"
        assert outcome["reason_code"] == "allow_escalation_approved"
