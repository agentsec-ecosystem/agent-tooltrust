"""Tests for audit session replay (M5 #81, F-08d).

Issue #81. ``replay_session`` reconstructs a session's cumulative state from
its audit entries alone; the integration tests drive the real ``ServerCore``
session path and assert the replayed cumulative risk and call counts exactly
match what the live ``SessionStore`` recorded.
"""

from __future__ import annotations

from agent_tooltrust.audit.models import AuditEntry
from agent_tooltrust.audit.replay import ReplayPoint, SessionReplay, replay_session
from agent_tooltrust.audit.sinks.jsonl import JsonlSink
from agent_tooltrust.engine.engine import Engine
from agent_tooltrust.policy.models import default_policy
from agent_tooltrust.server.server_core import ServerCore
from agent_tooltrust.server.session_store import SessionStore


def make_entry(
    *,
    session_id: str = "sess_1",
    timestamp: str,
    tool: str = "query_logs",
    action: str = "read",
    decision: str = "allow",
    criticality: str = "low",
    reason_code: str = "allow_low_risk",
    call_id: str | None = None,
    dry_run: bool = False,
) -> AuditEntry:
    """Build a minimal audit entry for replay tests."""
    return AuditEntry(
        session_id=session_id,
        timestamp=timestamp,
        tool=tool,
        tool_category="network",
        action=action,
        action_class="read",
        environment="staging",
        data_class="internal",
        agent_id="dev-eng",
        agent_class="core",
        decision=decision,
        criticality=criticality,
        reason_code=reason_code,
        explanation="x",
        call_id=call_id or f"call_{timestamp}",
        dry_run=dry_run,
    )


class TestReplayOrdering:
    def test_empty_entries_return_empty_replay(self) -> None:
        replay = replay_session([])
        assert isinstance(replay, SessionReplay)
        assert replay.session_id is None
        assert replay.points == []
        assert replay.call_count == 0
        assert replay.cumulative_risk == 0.0

    def test_out_of_order_entries_are_sorted_by_timestamp(self) -> None:
        replay = replay_session(
            [
                make_entry(timestamp="2026-01-01T03:00:00+00:00"),
                make_entry(timestamp="2026-01-01T01:00:00+00:00"),
                make_entry(timestamp="2026-01-01T02:00:00+00:00"),
            ]
        )
        assert [p.timestamp for p in replay.points] == [
            "2026-01-01T01:00:00+00:00",
            "2026-01-01T02:00:00+00:00",
            "2026-01-01T03:00:00+00:00",
        ]
        assert [p.index for p in replay.points] == [1, 2, 3]

    def test_session_id_defaults_to_first_entry(self) -> None:
        replay = replay_session([make_entry(timestamp="2026-01-01T01:00:00+00:00")])
        assert replay.session_id == "sess_1"

    def test_explicit_session_id_overrides(self) -> None:
        replay = replay_session(
            [make_entry(timestamp="2026-01-01T01:00:00+00:00")], session_id="forced"
        )
        assert replay.session_id == "forced"


class TestReplayCumulativeRisk:
    def test_allow_calls_accumulate_default_falloff(self) -> None:
        replay = replay_session(
            [
                make_entry(timestamp="2026-01-01T01:00:00+00:00", criticality="low"),
                make_entry(timestamp="2026-01-01T02:00:00+00:00", criticality="high"),
            ]
        )
        assert [p.risk_increment for p in replay.points] == [0.25, 0.25]
        assert [p.cumulative_risk for p in replay.points] == [0.25, 0.5]
        assert replay.cumulative_risk == 0.5

    def test_critical_call_accumulates_full_falloff(self) -> None:
        replay = replay_session(
            [make_entry(timestamp="2026-01-01T01:00:00+00:00", criticality="critical")]
        )
        assert replay.points[0].risk_increment == 1.0
        assert replay.cumulative_risk == 1.0

    def test_deny_adds_no_risk(self) -> None:
        replay = replay_session(
            [
                make_entry(timestamp="2026-01-01T01:00:00+00:00", criticality="low"),
                make_entry(
                    timestamp="2026-01-01T02:00:00+00:00",
                    decision="deny",
                    criticality="critical",
                    reason_code="deny_out_of_scope",
                ),
                make_entry(timestamp="2026-01-01T03:00:00+00:00", criticality="low"),
            ]
        )
        assert [p.risk_increment for p in replay.points] == [0.25, 0.0, 0.25]
        assert [p.cumulative_risk for p in replay.points] == [0.25, 0.25, 0.5]
        assert replay.cumulative_risk == 0.5

    def test_deny_counts_and_call_ids_captured(self) -> None:
        replay = replay_session(
            [
                make_entry(timestamp="2026-01-01T01:00:00+00:00"),
                make_entry(timestamp="2026-01-01T02:00:00+00:00", decision="deny"),
                make_entry(timestamp="2026-01-01T03:00:00+00:00"),
            ]
        )
        assert replay.deny_count == 1
        assert replay.denies == ["call_2026-01-01T02:00:00+00:00"]

    def test_call_count_tracks_accepted_calls_only(self) -> None:
        replay = replay_session(
            [
                make_entry(timestamp="2026-01-01T01:00:00+00:00"),
                make_entry(timestamp="2026-01-01T02:00:00+00:00", decision="deny"),
                make_entry(timestamp="2026-01-01T03:00:00+00:00"),
                make_entry(timestamp="2026-01-01T04:00:00+00:00"),
            ]
        )
        assert [p.call_count for p in replay.points] == [1, 1, 2, 3]
        assert replay.call_count == 4

    def test_dry_run_flag_is_forwarded(self) -> None:
        replay = replay_session(
            [
                make_entry(timestamp="2026-01-01T01:00:00+00:00", dry_run=True),
                make_entry(timestamp="2026-01-01T02:00:00+00:00"),
            ]
        )
        assert [p.dry_run for p in replay.points] == [True, False]

    def test_to_dict_shape(self) -> None:
        replay = replay_session(
            [make_entry(timestamp="2026-01-01T01:00:00+00:00", decision="deny")]
        )
        payload = replay.to_dict()
        assert payload["session_id"] == "sess_1"
        assert payload["call_count"] == 1
        assert payload["deny_count"] == 1
        assert payload["cumulative_risk"] == 0.0
        assert payload["denied_call_ids"] == ["call_2026-01-01T01:00:00+00:00"]
        assert len(payload["points"]) == 1
        assert payload["points"][0]["index"] == 1


class TestReplayPoint:
    def test_to_dict(self) -> None:
        point = ReplayPoint(
            index=1,
            call_id="c1",
            timestamp="2026-01-01T01:00:00+00:00",
            tool="query_logs",
            action="read",
            decision="allow",
            criticality="low",
            reason_code="allow_low_risk",
            risk_increment=0.25,
            cumulative_risk=0.25,
            call_count=1,
            dry_run=False,
        )
        payload = point.to_dict()
        assert payload["index"] == 1
        assert payload["cumulative_risk"] == 0.25
        assert payload["dry_run"] is False


class TestReplayMatchesLiveSession:
    """The core M5 #81 guarantee: replay reproduces live session state."""

    def test_cumulative_risk_matches_store(self, tmp_path) -> None:
        sink = JsonlSink(str(tmp_path / "audit.jsonl"))
        from agent_tooltrust.audit.logger import AuditLogger

        core = ServerCore(
            engine=Engine(default_policy("balanced")),
            session_store=SessionStore(),
            audit_logger=AuditLogger(sink),
        )
        sid = "sess_live"
        live_risk: list[float] = []
        for tool, action, env, data in [
            ("query_logs", "read", "staging", "internal"),
            ("deploy_service", "write", "production", "restricted"),
            ("drop_database", "delete", "production", "restricted"),
            ("query_metrics", "read", "staging", "internal"),
        ]:
            result = core.evaluate(
                tool,
                action,
                environment=env,
                data_class=data,
                agent_id="release-bot",
                session_id=sid,
            )
            live_risk.append(result["session_risk_score"])

        replay = replay_session(core.audit_logger.query(sid))
        assert replay.session_id == sid
        assert replay.call_count == 4
        # Denied call adds no risk → store round-trips to the same total.
        assert replay.cumulative_risk == live_risk[-1]
        # Every replayed step reproduces the live cumulative risk at that call.
        for point, expected in zip(replay.points, live_risk, strict=True):
            assert point.cumulative_risk == expected, point

    def test_replay_matches_store_for_deny_session(self, tmp_path) -> None:
        sink = JsonlSink(str(tmp_path / "audit.jsonl"))
        from agent_tooltrust.audit.logger import AuditLogger

        core = ServerCore(
            engine=Engine(default_policy("balanced")),
            session_store=SessionStore(),
            audit_logger=AuditLogger(sink),
        )
        sid = "sess_deny"
        core.evaluate(
            "drop_database", "delete", environment="production", data_class="restricted",
            agent_id="release-bot", session_id=sid,
        )
        replay = replay_session(core.audit_logger.query(sid))
        assert replay.deny_count == 1
        assert replay.cumulative_risk == 0.0
        state = core.session_store.get(sid)
        assert state is not None
        assert state.risk_score == replay.cumulative_risk

    def test_replay_from_sqlite_sink(self, tmp_path) -> None:
        from agent_tooltrust.audit.logger import AuditLogger
        from agent_tooltrust.audit.sinks.sqlite import SqliteSink

        db = str(tmp_path / "audit.db")
        sink = SqliteSink(db)
        core = ServerCore(
            engine=Engine(default_policy("balanced")),
            session_store=SessionStore(),
            audit_logger=AuditLogger(sink),
        )
        sid = "sess_sqlite"
        core.evaluate(
            "query_logs", "read", environment="staging", data_class="internal",
            agent_id="dev-eng", session_id=sid,
        )
        core.evaluate(
            "deploy_service", "write", environment="production", data_class="restricted",
            agent_id="dev-eng", session_id=sid,
        )
        replay = replay_session(core.audit_logger.query(sid))
        assert replay.call_count == 2
        assert replay.cumulative_risk > 0.0
        state = core.session_store.get(sid)
        assert state is not None
        assert replay.points[-1].cumulative_risk == state.risk_score
