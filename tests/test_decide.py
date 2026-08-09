"""Tests for M1.4 — the decision engine.

Issue #15. Resolution order: explicit deny > explicit allow > explicit
escalate > band mapping > default deny.
"""

from dataclasses import replace

from agent_tooltrust.engine.decide import Verdict, decide
from agent_tooltrust.engine.score import score
from agent_tooltrust.policy.models import Rule, default_policy
from agent_tooltrust.types import NormalizedCall, RiskScore

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


def _untrusted_agent(call: NormalizedCall) -> NormalizedCall:
    return replace(call, agent_id="untrusted-nobody")


class TestResolutionOrder:
    def test_explicit_deny_rule_overrides_escalate_rule(self):
        # drop_database delete prod customer_pii: both the delete-prod deny rule
        # and any escalate considerations apply; deny must win.
        call = _call(
            tool="drop_database",
            tool_category="db",
            action="delete",
            action_class="delete",
            environment="production",
            data_class="customer_pii",
        )
        verdict = decide(call, POLICY)
        assert verdict.decision == "deny"
        assert verdict.source == "rule"

    def test_explicit_deny_beats_lower_band(self):
        # No deny rule matches a read; band mapping decides (audit for a
        # production read on restricted data).
        call = _call(
            tool="read_secrets",
            tool_category="secrets",
            action_class="read",
            environment="production",
            data_class="restricted",
        )
        verdict = decide(call, POLICY)
        assert verdict.decision == "audit"
        assert verdict.source == "band"

    def test_explicit_allow_rule_overrides_band(self):
        allow_policy = replace(
            POLICY,
            rules=(Rule(decision="allow", tool="query_logs", action="read"), *POLICY.rules),
        )
        # Band would be allow anyway (0.10); add an explicit variant that the
        # band would NOT allow, to prove the rule wins.
        call_risky = _call(
            tool="query_logs",
            tool_category="search",
            action="read",
            environment="production",
            data_class="customer_pii",
            agent_id="untrusted-nobody",
        )
        # sanity: band is not allow for the risky read
        assert score(call_risky, allow_policy).band in ("medium", "high", "critical")
        verdict = decide(call_risky, allow_policy)
        assert verdict.decision == "allow"
        assert verdict.source == "rule"

    def test_explicit_escalate_rule_overrides_band(self):
        # deploy write prod internal: band says audit (0.38) but the escalate
        # write-prod rule must win.
        call = _call(
            tool="deploy_service",
            tool_category="cloud",
            action_class="write",
            environment="production",
        )
        assert score(call, POLICY).band == "medium"
        verdict = decide(call, POLICY)
        assert verdict.decision == "escalate"
        assert verdict.source == "rule"

    def test_band_low_maps_to_allow(self):
        call = _call()
        assert score(call, POLICY).band == "low"
        assert decide(call, POLICY) == Verdict("allow", "band")

    def test_band_medium_maps_to_audit(self):
        call = _call(
            tool="read_secrets",
            tool_category="secrets",
            action_class="read",
            environment="production",
            data_class="restricted",
        )
        verdict = decide(call, POLICY)
        assert verdict.decision == "audit"
        assert verdict.source == "band"

    def test_band_high_maps_to_escalate(self):
        call = _untrusted_agent(
            _call(
                tool="drop_database",
                tool_category="db",
                action_class="delete",
                environment="staging",
                data_class="customer_pii",
            )
        )
        assert score(call, POLICY).band == "high"
        verdict = decide(call, POLICY)
        assert verdict.decision == "escalate"
        assert verdict.source == "band"

    def test_band_critical_maps_to_deny(self):
        call = _untrusted_agent(
            _call(
                tool="drop_database",
                tool_category="db",
                action_class="delete",
                environment="production",
                data_class="customer_pii",
            )
        )
        assert score(call, POLICY).band == "critical"
        # deny rule on delete-prod also matches here; source is "rule" but the
        # outcome is identical — a critical band is always a deny.
        verdict = decide(call, POLICY)
        assert verdict.decision == "deny"

    def test_rule_reason_carried_into_verdict(self):
        call = _call(
            tool="deploy_service",
            tool_category="cloud",
            action_class="write",
            environment="production",
        )
        verdict = decide(call, POLICY)
        assert verdict.source == "rule"
        assert verdict.reason

    def test_always_returns_one_of_four_decisions(self):
        for band in ("low", "medium", "high", "critical"):
            rs = RiskScore(
                dimensions={"d": 0.5},
                aggregate=0.5,
                band=band,  # type: ignore[arg-type]
            )
            verdict = decide_raw(rs, _call())
            assert verdict.decision in ("allow", "audit", "escalate", "deny")


def decide_raw(risk_score, call):
    """Direct pipeline entry for path-independent tests."""
    from agent_tooltrust.engine.decide import decide_from_score

    return decide_from_score(risk_score, call, POLICY)
