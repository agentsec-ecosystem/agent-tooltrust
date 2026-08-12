"""Tests for M3.1 — the ``AuditEntry`` model.

Issue #24 (F-31). ``AuditEntry`` carries every field the audit trail needs,
serializes to a JSON-friendly dict, and round-trips back without loss.
"""

from agent_tooltrust.audit.models import AuditEntry
from agent_tooltrust.engine.engine import Engine
from agent_tooltrust.engine.normalize import normalize
from agent_tooltrust.policy.models import default_policy
from agent_tooltrust.types import Factor


def make_call(session_id: str = "sess_1"):
    return normalize(
        tool="deploy_service",
        action="deploy",
        environment="production",
        data_class="restricted",
        agent_id="dev-eng",
        agent_class="engineer",
        session_id=session_id,
    )


def make_decision(**overrides):
    engine = Engine(default_policy("balanced"))
    return engine.evaluate(
        tool_name="deploy_service",
        action="deploy",
        environment="production",
        data_class="restricted",
        agent_id="dev-eng",
        **overrides,
    )


class TestAuditEntryFields:
    def test_from_decision_populates_all_fields(self):
        entry = AuditEntry.from_decision(make_decision(), make_call())
        assert entry.session_id == "sess_1"
        assert entry.tool == "deploy_service"
        assert entry.tool_category == "cloud"
        assert entry.action == "deploy"
        assert entry.action_class == "write"
        assert entry.environment == "production"
        assert entry.data_class == "restricted"
        assert entry.agent_id == "dev-eng"
        assert entry.agent_class == "engineer"
        assert entry.decision == "escalate"
        assert entry.criticality == "high"
        assert entry.reason_code == "escalate_prod_write"
        assert entry.explanation
        assert len(entry.factors) == 5
        assert entry.policy_version == "1.0.0"
        assert entry.dry_run is False
        assert entry.escalation_id is not None

    def test_timestamp_is_iso_utc(self):
        entry = AuditEntry.from_decision(make_decision(), make_call())
        assert "+00:00" in entry.timestamp

    def test_session_defaults_from_call(self):
        entry = AuditEntry.from_decision(make_decision(), make_call("call_session"))
        assert entry.session_id == "call_session"

    def test_explicit_session_wins(self):
        entry = AuditEntry.from_decision(
            make_decision(), make_call("call_session"), session_id="explicit"
        )
        assert entry.session_id == "explicit"

    def test_approver_recorded(self):
        entry = AuditEntry.from_decision(make_decision(), make_call(), approver="alice")
        assert entry.approver == "alice"


class TestAuditEntrySerialization:
    def test_to_dict_serializes_factors(self):
        data = make_decision().to_dict()
        assert isinstance(data["factors"], list)
        for factor in data["factors"]:
            assert set(factor) == {"dimension", "value", "contribution"}

    def test_round_trip_via_dict(self):
        entry = AuditEntry.from_decision(make_decision(), make_call())
        assert AuditEntry.from_dict(entry.to_dict()) == entry

    def test_from_dict_tolerates_missing_optionals(self):
        data = AuditEntry.from_decision(make_decision(), make_call()).to_dict()
        for key in ("tool_category", "action_class", "agent_class", "escalation_id", "approver"):
            data.pop(key, None)
        entry = AuditEntry.from_dict(data)
        assert entry.tool_category is None
        assert entry.action_class is None
        assert entry.approver is None

    def test_dry_run_flag_override(self):
        entry = AuditEntry.from_decision(make_decision(), make_call(), dry_run=True)
        assert entry.dry_run is True

    def test_dry_run_defaults_from_decision(self):
        entry = AuditEntry.from_decision(make_decision(), make_call())
        assert entry.dry_run is False


class TestAuditEntryFactors:
    def test_explicit_factors_preserved(self):
        from agent_tooltrust.types import Decision

        decision = Decision(
            decision="deny",
            criticality="critical",
            reason_code="deny_critical_op",
            explanation="blocked",
            factors=[Factor("environment", "production", 0.8)],
        )
        entry = AuditEntry.from_decision(decision, make_call())
        assert entry.factors[0].value == "production"
        assert entry.factors[0].contribution == 0.8
