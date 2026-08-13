"""Engine → audit-logger integration tests (M3.7).

Issue #24 (F-33). ``Engine`` records every decision to the configured sink
after stage 5, logs the real (pre-dry-run) decision in shadow mode, and never
lets an audit failure block or change the decision.
"""

from agent_tooltrust.audit.logger import AuditLogger
from agent_tooltrust.audit.sink import AuditSink
from agent_tooltrust.audit.sinks.jsonl import JsonlSink
from agent_tooltrust.engine.engine import Engine
from agent_tooltrust.policy.models import default_policy


class TestEngineAudit:
    def test_evaluate_records_entry(self, tmp_path):
        path = tmp_path / "audit.jsonl"
        sink = JsonlSink(str(path))
        engine = Engine(
            default_policy("balanced"),
            audit_logger=AuditLogger(sink),
        )
        engine.evaluate(
            tool_name="deploy_service",
            action="deploy",
            environment="production",
            data_class="restricted",
            agent_id="dev-eng",
        )
        entries = sink.query()
        assert len(entries) == 1
        assert entries[0].tool == "deploy_service"
        assert entries[0].agent_id == "dev-eng"
        assert entries[0].dry_run is False

    def test_allow_decision_is_logged(self, tmp_path):
        path = tmp_path / "audit.jsonl"
        sink = JsonlSink(str(path))
        engine = Engine(default_policy("balanced"), audit_logger=AuditLogger(sink))
        engine.evaluate(
            tool_name="query_logs",
            action="read",
            environment="staging",
            data_class="internal",
            agent_id="release-bot",
        )
        entries = sink.query()
        assert len(entries) == 1
        assert entries[0].decision == "allow"

    def test_dry_run_logs_real_decision(self, tmp_path):
        path = tmp_path / "audit.jsonl"
        sink = JsonlSink(str(path))
        engine = Engine(
            default_policy("balanced"),
            dry_run=True,
            audit_logger=AuditLogger(sink),
        )
        decision = engine.evaluate(
            tool_name="deploy_service",
            action="deploy",
            environment="production",
            data_class="restricted",
            agent_id="dev-eng",
        )
        assert decision.decision == "allow"
        assert decision.dry_run is True
        entries = sink.query()
        assert len(entries) == 1
        assert entries[0].dry_run is True
        assert entries[0].decision == "escalate"

    def test_no_audit_logger_is_fine(self):
        engine = Engine(default_policy("balanced"))
        decision = engine.evaluate(
            tool_name="deploy_service",
            action="deploy",
            environment="production",
            data_class="restricted",
            agent_id="dev-eng",
        )
        assert decision.decision == "escalate"

    def test_failing_sink_never_blocks_decision(self, tmp_path):
        class BoomSink(AuditSink):
            def write(self, entry) -> None:
                raise OSError("disk full")

            def query(self, session_id=None):
                raise OSError("disk full")

        engine = Engine(
            default_policy("balanced"),
            audit_logger=AuditLogger(BoomSink()),
        )
        decision = engine.evaluate(
            tool_name="deploy_service",
            action="deploy",
            environment="production",
            data_class="restricted",
            agent_id="dev-eng",
        )
        assert decision.decision in ("allow", "audit", "escalate", "deny")

    def test_entries_in_sqlite_sink(self, tmp_path):
        path = tmp_path / "audit.db"
        from agent_tooltrust.audit.sinks.sqlite import SqliteSink

        sink = SqliteSink(str(path))
        engine = Engine(default_policy("balanced"), audit_logger=AuditLogger(sink))
        engine.evaluate(
            tool_name="deploy_service",
            action="deploy",
            environment="production",
            data_class="restricted",
            agent_id="dev-eng",
        )
        entries = sink.query()
        assert len(entries) == 1
        assert entries[0].tool == "deploy_service"
