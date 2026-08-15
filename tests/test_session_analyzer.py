"""Tests for the session analytics analyzer."""

from __future__ import annotations

from agent_tooltrust.analytics.session_analyzer import (
    analyze,
)
from agent_tooltrust.audit.models import AuditEntry
from agent_tooltrust.policy.models import Policy, Rule


def _entry(
    tool: str = "query_logs",
    action: str = "read",
    environment: str = "staging",
    data_class: str = "internal",
    agent_id: str = "bot1",
    decision: str = "allow",
    reason_code: str = "",
    timestamp: str = "2026-01-01T00:00:00",
) -> AuditEntry:
    return AuditEntry(
        session_id="s1",
        timestamp=timestamp,
        tool=tool,
        tool_category=None,
        action=action,
        action_class=None,
        environment=environment,
        data_class=data_class,
        agent_id=agent_id,
        agent_class=None,
        decision=decision,
        criticality="low",
        reason_code=reason_code,
        explanation="",
    )


def _policy_with_rules(*rules: Rule) -> Policy:
    return Policy(
        version="1.0",
        posture="balanced",
        environments={"development": 0.0, "staging": 0.1, "production": 0.7},
        data_classes={"public": 0.0, "internal": 0.2},
        risk_weights={},
        rules=rules,
        agents={},
    )


class TestRecurringDenials:
    def test_no_denials_returns_empty(self) -> None:
        entries = [_entry(decision="allow"), _entry(decision="allow")]
        result = analyze(entries)
        assert result.recurring_denials == []

    def test_single_denial_below_min(self) -> None:
        entries = [
            _entry(tool="drop_database", action="delete", decision="deny", reason_code="blocked"),
            _entry(decision="allow"),
        ]
        result = analyze(entries, min_denials=3)
        assert result.recurring_denials == []

    def test_recurring_denials_surfaced(self) -> None:
        entries = [
            _entry(
                tool="run_query", action="write", environment="production",
                data_class="customer_pii", agent_id="bot1",
                decision="deny", reason_code="write_blocked",
            ),
            _entry(
                tool="run_query", action="write", environment="production",
                data_class="customer_pii", agent_id="bot1",
                decision="deny", reason_code="write_blocked",
            ),
            _entry(
                tool="run_query", action="write", environment="production",
                data_class="customer_pii", agent_id="bot1",
                decision="deny", reason_code="write_blocked",
            ),
            _entry(decision="allow"),
        ]
        result = analyze(entries, min_denials=3)
        assert len(result.recurring_denials) == 1
        rd = result.recurring_denials[0]
        assert rd.deny_count == 3
        assert rd.sample_reason == "write_blocked"

    def test_recurring_not_surfaced_when_allow_exists(self) -> None:
        entries = [
            _entry(
                tool="run_query", action="write", environment="production",
                data_class="customer_pii", agent_id="bot1",
                decision="deny", reason_code="write_blocked",
            ),
            _entry(
                tool="run_query", action="write", environment="production",
                data_class="customer_pii", agent_id="bot1",
                decision="deny", reason_code="write_blocked",
            ),
            _entry(
                tool="run_query", action="write", environment="production",
                data_class="customer_pii", agent_id="bot1",
                decision="deny", reason_code="write_blocked",
            ),
            _entry(
                tool="run_query", action="write", environment="production",
                data_class="customer_pii", agent_id="bot1",
                decision="allow",
            ),
        ]
        result = analyze(entries, min_denials=3)
        assert result.recurring_denials == []


class TestDenyToAllowTransitions:
    def test_no_transition_returns_empty(self) -> None:
        entries = [_entry(decision="allow"), _entry(decision="allow")]
        result = analyze(entries)
        assert result.deny_to_allow_transitions == []

    def test_deny_then_allow_same_context(self) -> None:
        entries = [
            _entry(
                tool="run_query", action="write", environment="production",
                data_class="customer_pii", agent_id="bot1",
                decision="deny", reason_code="blocked",
                timestamp="2026-01-01T00:00:00",
            ),
            _entry(
                tool="run_query", action="write", environment="production",
                data_class="customer_pii", agent_id="bot1",
                decision="allow",
                timestamp="2026-01-02T00:00:00",
            ),
        ]
        result = analyze(entries)
        assert len(result.deny_to_allow_transitions) == 1
        t = result.deny_to_allow_transitions[0]
        assert "2026-01-01" in t.first_deny_at
        assert "2026-01-02" in t.first_allow_at


class TestDeadRules:
    def test_no_policy_returns_empty(self) -> None:
        entries = [_entry(decision="deny", reason_code="blocked")]
        result = analyze(entries)
        assert result.dead_rules == []

    def test_rule_that_matched_not_dead(self) -> None:
        rules = [Rule(decision="deny", action="delete", reason="delete_blocked")]
        entries = [
            _entry(
                tool="drop_database", action="delete", decision="deny",
                reason_code="delete_blocked",
            ),
        ]
        policy = _policy_with_rules(*rules)
        result = analyze(entries, policy=policy)
        assert result.dead_rules == []

    def test_rule_that_never_matched_is_dead(self) -> None:
        rules = [Rule(decision="deny", action="delete", reason="delete_blocked")]
        entries = [_entry(decision="allow")]
        policy = _policy_with_rules(*rules)
        result = analyze(entries, policy=policy)
        assert len(result.dead_rules) == 1
        assert result.dead_rules[0].reason == "delete_blocked"


class TestOverHitRules:
    def test_empty_returns_empty(self) -> None:
        result = analyze([])
        assert result.over_hit_rules == []

    def test_rule_above_percentile_surfaced(self) -> None:
        entries = [
            _entry(decision="deny", reason_code="rare", timestamp=f"2026-01-{d:02d}T00:00:00")
            for d in range(1, 2)
        ] + [
            _entry(decision="deny", reason_code="frequent", timestamp=f"2026-01-{d:02d}T00:00:00")
            for d in range(1, 20)
        ]
        result = analyze(entries)
        codes = {r.reason_code for r in result.over_hit_rules}
        assert "frequent" in codes
