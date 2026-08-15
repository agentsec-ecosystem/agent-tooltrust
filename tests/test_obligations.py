"""Tests for M1 #147 — permit-with-obligation (DD-20).

The outcome set gains ``allow_with_obligation``: the call is allowed but the
gatekeeper must perform one or more mandatory side-effects (first-use sign-off,
auto-notify + review ticket, signed audit entry). Obligations are enforced by
the engine, never delegated to agent cooperation, and a runner failure is
fail-closed (deny, never allow-without-obligation).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from agent_tooltrust.engine.engine import Engine
from agent_tooltrust.engine.obligations import ObligationError, ObligationStore, run_obligations
from agent_tooltrust.policy.models import Policy, Rule, default_policy


def _policy(*rules: Rule) -> Policy:
    base = default_policy("balanced")
    return Policy(
        version=base.version,
        posture=base.posture,
        environments=base.environments,
        data_classes=base.data_classes,
        risk_weights=base.risk_weights,
        rules=tuple(rules),
        agents=base.agents,
    )


def _now() -> datetime:
    return datetime(2026, 8, 13, 12, 0, 0, tzinfo=UTC)


class TestObligationStore:
    def test_first_use_not_signed_off(self) -> None:
        store = ObligationStore()
        assert store.is_signed_off("release-bot", "drop_database", _now()) is False

    def test_grant_caches_sign_off(self) -> None:
        store = ObligationStore()
        store.grant("release-bot", "drop_database", _now())
        assert store.is_signed_off("release-bot", "drop_database", _now()) is True

    def test_ttl_expiry_re_requires_sign_off(self) -> None:
        store = ObligationStore(ttl_seconds=60)
        t0 = _now()
        store.grant("release-bot", "drop_database", t0)
        assert store.is_signed_off("release-bot", "drop_database", t0) is True
        later = datetime(2026, 8, 13, 12, 5, 0, tzinfo=UTC)  # +5 min
        assert store.is_signed_off("release-bot", "drop_database", later) is False

    def test_sign_off_is_scoped_to_agent_and_tool(self) -> None:
        store = ObligationStore()
        store.grant("release-bot", "drop_database", _now())
        assert store.is_signed_off("other-bot", "drop_database", _now()) is False
        assert store.is_signed_off("release-bot", "other_tool", _now()) is False


class TestRunObligations:
    def test_unknown_obligation_fails_closed(self) -> None:
        with pytest.raises(ObligationError):
            run_obligations(
                ("no_such_obligation",),
                store=ObligationStore(),
                agent_id="release-bot",
                tool="drop_database",
                now=_now(),
            )

    def test_first_use_signoff_grants_on_first_use(self) -> None:
        store = ObligationStore()
        results = run_obligations(
            ("first_use_signoff",),
            store=store,
            agent_id="release-bot",
            tool="drop_database",
            now=_now(),
        )
        assert "drop_database" in results
        assert store.is_signed_off("release-bot", "drop_database", _now()) is True

    def test_first_use_signoff_reports_cached_on_subsequent(self) -> None:
        store = ObligationStore()
        run_obligations(
            ("first_use_signoff",),
            store=store,
            agent_id="release-bot",
            tool="drop_database",
            now=_now(),
        )
        results = run_obligations(
            ("first_use_signoff",),
            store=store,
            agent_id="release-bot",
            tool="drop_database",
            now=_now(),
        )
        assert "cached" in results.lower()

    def test_auto_notify_records_event(self) -> None:
        store = ObligationStore()
        results = run_obligations(
            ("auto_notify",),
            store=store,
            agent_id="release-bot",
            tool="drop_database",
            now=_now(),
        )
        assert "notified" in results.lower()
        assert len(store.events) == 1

    def test_signed_audit_writes_immutable_entry(self) -> None:
        store = ObligationStore()
        results = run_obligations(
            ("signed_audit",),
            store=store,
            agent_id="release-bot",
            tool="drop_database",
            now=_now(),
        )
        assert "signed" in results.lower()
        assert len(store.events) == 1

    def test_multiple_obligations_all_fire(self) -> None:
        store = ObligationStore()
        results = run_obligations(
            ("first_use_signoff", "auto_notify", "signed_audit"),
            store=store,
            agent_id="release-bot",
            tool="drop_database",
            now=_now(),
        )
        assert len(results.split("; ")) == 3


class TestEnginePermitWithObligation:
    def _engine(self, store: ObligationStore | None = None) -> Engine:
        return Engine(
            _policy(
                Rule(
                    decision="allow",
                    action="delete",
                    environment="production",
                    obligations=("first_use_signoff",),
                )
            ),
            obligation_store=store,
        )

    def test_matching_call_resolves_allow_with_obligation(self) -> None:
        decision = self._engine().evaluate(
            tool_name="drop_database",
            action="delete",
            environment="production",
            data_class="restricted",
            agent_id="release-bot",
        )
        assert decision.decision == "allow_with_obligation"
        assert decision.obligations == ("first_use_signoff",)

    def test_sign_off_cached_then_plain_call(self) -> None:
        store = ObligationStore()
        engine = self._engine(store)
        engine.evaluate(
            tool_name="drop_database",
            action="delete",
            environment="production",
            data_class="restricted",
            agent_id="release-bot",
        )
        second = engine.evaluate(
            tool_name="drop_database",
            action="delete",
            environment="production",
            data_class="restricted",
            agent_id="release-bot",
        )
        # Sign-off now cached → obligation still declared, decision unchanged.
        assert store.is_signed_off("release-bot", "drop_database", _now()) is True
        assert second.decision == "allow_with_obligation"

    def test_non_matching_call_untouched(self) -> None:
        engine = self._engine()
        decision = engine.evaluate(
            tool_name="query_logs",
            action="read",
            environment="development",
            data_class="public",
            agent_id="release-bot",
        )
        assert decision.decision != "allow_with_obligation"

    def test_rule_without_obligations_plain_allow(self) -> None:
        engine = Engine(
            _policy(Rule(decision="allow", action="write", environment="production"))
        )
        decision = engine.evaluate(
            tool_name="deploy_service",
            action="write",
            environment="production",
            data_class="internal",
            agent_id="release-bot",
        )
        assert decision.decision != "allow_with_obligation"

    def test_unknown_obligation_in_rule_fails_closed(self) -> None:
        engine = Engine(
            _policy(
                Rule(
                    decision="allow",
                    action="delete",
                    environment="production",
                    obligations=("no_such",),
                )
            )
        )
        decision = engine.evaluate(
            tool_name="drop_database",
            action="delete",
            environment="production",
            data_class="restricted",
            agent_id="release-bot",
        )
        assert decision.decision == "deny"
        assert decision.reason_code == "deny_obligation_failed"

    def test_obligation_summary_in_explanation_and_audit_ready(self) -> None:
        engine = self._engine()
        decision = engine.evaluate(
            tool_name="drop_database",
            action="delete",
            environment="production",
            data_class="restricted",
            agent_id="release-bot",
        )
        assert "OBLIGATIONS" in decision.explanation
        assert "drop_database" in decision.explanation
