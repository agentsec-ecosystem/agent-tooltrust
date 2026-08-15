"""Tests for the deterministic demo-data seeder (M7.5)."""

from __future__ import annotations

from agent_tooltrust.audit.logger import AuditLogger
from agent_tooltrust.engine.engine import Engine
from agent_tooltrust.engine.escalation import EscalationStatus
from agent_tooltrust.policy.models import default_policy
from agent_tooltrust.server.seed import (
    SEED_CALLS,
    SEED_ESCALATIONS,
    seed_audit,
    seed_demo_data,
    seed_escalations,
)
from agent_tooltrust.server.server_core import ServerCore
from agent_tooltrust.server.session_store import SessionStore


def _core() -> ServerCore:
    return ServerCore(
        engine=Engine(default_policy("balanced")),
        session_store=SessionStore(),
        audit_logger=AuditLogger(),
    )


def test_seed_audit_writes_entries(tmp_path):
    from agent_tooltrust.audit.sinks.jsonl import JsonlSink

    sink = JsonlSink(str(tmp_path / "audit.jsonl"))
    core = ServerCore(
        engine=Engine(default_policy("balanced")),
        session_store=SessionStore(),
        audit_logger=AuditLogger(sink=sink),
    )
    count = seed_audit(core)
    assert count == len(SEED_CALLS)
    entries = core.audit_logger.query("demo-session")
    assert len(entries) == len(SEED_CALLS)


def test_seed_escalations_spans_all_states():
    core = _core()
    count = seed_escalations(core)
    assert count == len(SEED_ESCALATIONS)
    records = core.escalation_manager.records
    statuses = {r.status for r in records.values()}
    assert statuses == {
        EscalationStatus.PENDING,
        EscalationStatus.APPROVED,
        EscalationStatus.DENIED,
        EscalationStatus.EXPIRED,
    }


def test_seed_demo_data_returns_counts():
    core = _core()
    result = seed_demo_data(core)
    assert result["audit"] == len(SEED_CALLS)
    assert result["escalations"] == len(SEED_ESCALATIONS)


def test_seed_is_deterministic():
    a = _core()
    b = _core()
    seed_demo_data(a)
    seed_demo_data(b)
    a_ids = sorted(a.escalation_manager.records)
    b_ids = sorted(b.escalation_manager.records)
    assert a_ids == b_ids


def test_approved_escalation_has_approver():
    core = _core()
    seed_escalations(core)
    approved = [
        r for r in core.escalation_manager.records.values()
        if r.status == EscalationStatus.APPROVED
    ]
    assert approved and all(r.approver for r in approved)


def test_expired_escalation_expires_in_past():
    core = _core()
    seed_escalations(core)
    expired = [
        r for r in core.escalation_manager.records.values()
        if r.status == EscalationStatus.EXPIRED
    ]
    assert expired and all(r.is_expired() for r in expired)
