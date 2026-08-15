"""Tests for M4 Task 1 (#143) — deny-storm / policy-probe detection.

A dense deny run must trip an action; a legit replan burst must not
false-positive. The analyzer is fed Decision + NormalizedCall pairs and
produces a pause/throttle/lock action from deny rate, consecutive denies,
escalation frequency, and tool-set entropy.
"""

from __future__ import annotations

from agent_tooltrust.engine.deny_storm import (
    LOCK,
    PAUSE,
    THROTTLE,
    DenyStormAnalyzer,
    DenyStormConfig,
)
from agent_tooltrust.engine.engine import Engine
from agent_tooltrust.errors import DENY_DENY_STORM
from agent_tooltrust.policy.models import default_policy
from agent_tooltrust.types import Decision, DecisionValue, NormalizedCall


def _call(tool: str, agent_id: str = "probe-bot") -> NormalizedCall:
    return NormalizedCall(
        tool=tool,
        tool_category="cloud",
        action="deploy",
        action_class="write",
        environment="production",
        data_class="restricted",
        agent_id=agent_id,
        agent_class="engineer",
    )


def _decision(kind: DecisionValue) -> Decision:
    return Decision(
        decision=kind,
        criticality="high",
        reason_code=f"reason_{kind}",
        explanation=f"{kind} decision",
    )


def _observe(
    analyzer: DenyStormAnalyzer, *kinds: DecisionValue, agent_id: str = "probe-bot"
) -> None:
    for index, kind in enumerate(kinds):
        analyzer.observe(_decision(kind), _call(f"tool_{index % 9}", agent_id))


def _run(kind: DecisionValue, count: int) -> tuple[DecisionValue, ...]:
    """A homogeneous run of *count* decisions of one kind."""
    return (kind,) * count


class TestSignals:
    def test_empty_analyzer_is_clear(self):
        analyzer = DenyStormAnalyzer()
        status = analyzer.status(None)
        assert status.observed == 0
        assert status.action is None

    def test_to_dict_round_trip(self):
        analyzer = DenyStormAnalyzer()
        _observe(analyzer, *_run("deny", 10))
        payload = analyzer.status("probe-bot").to_dict()
        assert payload["session"] == "probe-bot"
        assert payload["deny_rate"] == 1.0
        assert payload["action"] == LOCK

    def test_config_property_exposed(self):
        config = DenyStormConfig(window_size=7)
        analyzer = DenyStormAnalyzer(config)
        assert analyzer.config is config

    def test_unknown_session_key_is_clear(self):
        analyzer = DenyStormAnalyzer()
        analyzer.observe(_decision("deny"), _call("git_push"))
        assert analyzer.status("nobody-knows").action is None

    def test_all_denies_trip_lock(self):
        analyzer = DenyStormAnalyzer()
        _observe(analyzer, *_run("deny", 10))
        status = analyzer.status("probe-bot")
        assert status.action == LOCK
        assert status.deny_rate == 1.0
        assert "entropy" in status.reason

    def test_consecutive_denies_trip_throttle_before_entropy(self):
        # Same tool every time -> entropy 0, so lock is off; the run length
        # trips throttle.
        analyzer = DenyStormAnalyzer()
        analyzer.observe(_decision("allow"), _call("tool_a"))
        for _ in range(DenyStormConfig().max_consecutive_denies):
            analyzer.observe(_decision("deny"), _call("tool_a"))
        status = analyzer.status("probe-bot")
        assert status.action == THROTTLE
        assert "consecutive" in status.reason

    def test_escalation_frequency_trips_pause(self):
        analyzer = DenyStormAnalyzer(
            DenyStormConfig(
                deny_rate_threshold=1.0,
                max_consecutive_denies=100,
            )
        )
        _observe(analyzer, *_run("escalate", 6))
        status = analyzer.status("probe-bot")
        assert status.action == PAUSE
        assert "escalations" in status.reason

    def test_deny_rate_trips_throttle_without_consecutive_run(self):
        # 7 denies and 3 allows interleaved (no long run), same tool so
        # entropy is 0: only the deny-rate signal can trip throttle.
        analyzer = DenyStormAnalyzer(DenyStormConfig(window_size=10, min_decisions=10))
        kinds: tuple[DecisionValue, ...] = (
            "deny", "allow", "deny", "deny", "allow", "deny", "allow", "deny", "deny", "deny",
        )
        for kind in kinds:
            analyzer.observe(_decision(kind), _call("deploy_service"))
        assert analyzer.status("probe-bot").action == THROTTLE

    def test_status_is_sorted_for_dashboards(self):
        analyzer = DenyStormAnalyzer()
        _observe(analyzer, *_run("deny", 8), agent_id="zzz")
        _observe(analyzer, *_run("deny", 8), agent_id="aaa")
        keys = [s.session_key for s in analyzer.statuses()]
        assert keys == sorted(keys)


class TestLegitBurstNoFalsePositive:
    def test_mixed_successful_session_is_clear(self):
        analyzer = DenyStormAnalyzer()
        _observe(analyzer, *_run("allow", 8))
        assert analyzer.status("probe-bot").action is None

    def test_short_replan_burst_below_min_decisions_is_clear(self):
        # A replan is a couple of retries, not a window-filling run.
        analyzer = DenyStormAnalyzer()
        _observe(analyzer, "deny", "allow", "deny", "allow")
        assert analyzer.status("probe-bot").action is None

    def test_replan_retries_same_tool_never_locks(self):
        # Replanning retries the SAME tool with different args: high deny rate
        # but entropy 0, so the lock signal (breadth + density) stays off.
        analyzer = DenyStormAnalyzer()
        for _ in range(12):
            analyzer.observe(_decision("deny"), _call("deploy_service"))
        status = analyzer.status("probe-bot")
        assert status.action != LOCK
        assert status.tool_entropy == 0.0

    def test_many_tools_but_low_deny_rate_is_clear(self):
        # Exploration can touch many tools (high entropy) while rarely denied.
        analyzer = DenyStormAnalyzer()
        tools = [f"tool_{i}" for i in range(9)]
        for i in range(18):
            analyzer.observe(_decision("allow"), _call(tools[i % 9]))
        assert analyzer.status("probe-bot").action is None


class TestReset:
    def test_reset_clears_one_session(self):
        analyzer = DenyStormAnalyzer()
        _observe(analyzer, *_run("deny", 10), agent_id="locked")
        _observe(analyzer, *_run("deny", 10), agent_id="other")
        analyzer.reset("locked")
        assert analyzer.status("locked").observed == 0
        assert analyzer.status("other").action == LOCK

    def test_reset_all(self):
        analyzer = DenyStormAnalyzer()
        _observe(analyzer, *_run("deny", 10))
        analyzer.reset_all()
        assert analyzer.status("probe-bot").observed == 0


class TestSessionCap:
    def test_oldest_session_evicted_at_cap(self):
        analyzer = DenyStormAnalyzer(DenyStormConfig(max_sessions=2))
        _observe(analyzer, *_run("deny", 10), agent_id="first")
        _observe(analyzer, *_run("deny", 10), agent_id="second")
        assert analyzer.status("first").observed == 10
        # Adding a third evicts the oldest (first).
        _observe(analyzer, *_run("deny", 10), agent_id="third")
        assert analyzer.status("first").observed == 0
        assert analyzer.status("second").observed == 10
        assert analyzer.status("third").observed == 10

    def test_cap_zero_rejected(self):
        try:
            DenyStormConfig(max_sessions=0)
            raise AssertionError("expected ValueError")
        except ValueError:
            pass


class TestConfigValidation:
    def test_bad_window_size(self):
        try:
            DenyStormConfig(window_size=0)
            raise AssertionError("expected ValueError")
        except ValueError:
            pass

    def test_bad_min_decisions(self):
        try:
            DenyStormConfig(min_decisions=0)
            raise AssertionError("expected ValueError")
        except ValueError:
            pass

    def test_bad_deny_rate(self):
        try:
            DenyStormConfig(deny_rate_threshold=1.5)
            raise AssertionError("expected ValueError")
        except ValueError:
            pass

    def test_bad_max_consecutive(self):
        try:
            DenyStormConfig(max_consecutive_denies=0)
            raise AssertionError("expected ValueError")
        except ValueError:
            pass

    def test_bad_escalation_threshold(self):
        try:
            DenyStormConfig(escalation_threshold=0)
            raise AssertionError("expected ValueError")
        except ValueError:
            pass

    def test_bad_entropy_threshold(self):
        try:
            DenyStormConfig(entropy_threshold=-0.1)
            raise AssertionError("expected ValueError")
        except ValueError:
            pass

    def test_raises_with_pytest(self):
        import pytest

        with pytest.raises(ValueError):
            DenyStormConfig(window_size=0)


class TestEngineIntegration:
    def test_engine_observes_deny_storm(self):
        engine = Engine(default_policy("balanced"))
        analyzer = engine.deny_storm_analyzer
        for _ in range(12):
            engine.evaluate(
                tool_name="deploy_service",
                action="deploy",
                environment="production",
                data_class="restricted",
                agent_id="probe-bot",
            )
        status = analyzer.status("probe-bot")
        assert status.observed >= 12
        assert status.action is not None

    def test_enforce_deny_storm_denies_new_calls(self):
        engine = Engine(
            default_policy("balanced"),
            enforce_deny_storm=True,
        )
        # Warm up a lock: the first 12 evaluates are scored (locked after the
        # storm trips), so use enough to cross the threshold with entropy.
        for _ in range(12):
            engine.evaluate(
                tool_name="deploy_service",
                action="deploy",
                environment="production",
                data_class="restricted",
                agent_id="probe-bot",
            )
        verdict = engine.evaluate(
            tool_name="deploy_service",
            action="deploy",
            environment="production",
            data_class="restricted",
            agent_id="probe-bot",
        )
        assert verdict.decision == "deny"
        assert verdict.reason_code == DENY_DENY_STORM

    def test_enforcement_off_is_observer_only(self):
        engine = Engine(default_policy("balanced"))
        for _ in range(12):
            engine.evaluate(
                tool_name="deploy_service",
                action="deploy",
                environment="production",
                data_class="restricted",
                agent_id="probe-bot",
            )
        verdict = engine.evaluate(
            tool_name="deploy_service",
            action="deploy",
            environment="production",
            data_class="restricted",
            agent_id="probe-bot",
        )
        assert verdict.decision != "deny" or verdict.reason_code != DENY_DENY_STORM
