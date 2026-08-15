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


def _policy_with_args_policy(args_policy):
    from agent_tooltrust.policy.models import Policy

    base = default_policy("balanced")
    return Policy(
        version=base.version,
        posture=base.posture,
        environments=base.environments,
        data_classes=base.data_classes,
        risk_weights=base.risk_weights,
        rules=base.rules,
        agents=base.agents,
        args_policy=args_policy,
    )


def _policy_with_obligation(obligations):
    from agent_tooltrust.policy.models import Policy, Rule

    base = default_policy("balanced")
    return Policy(
        version=base.version,
        posture=base.posture,
        environments=base.environments,
        data_classes=base.data_classes,
        risk_weights=base.risk_weights,
        rules=(
            Rule(
                decision="allow",
                action="delete",
                environment="production",
                obligations=obligations,
            ),
        ),
        agents=base.agents,
    )


class TestEarlyReturnDeniesAreAudited:
    """Argument-policy (1b) and obligation-failure (4b) denies must be
    recorded in the audit trail and must still honor dry-run semantics."""

    def test_argument_policy_deny_is_audited(self, tmp_path):
        from agent_tooltrust.engine.argument_policy import ArgumentSpec

        sink = JsonlSink(str(tmp_path / "audit.jsonl"))
        policy = _policy_with_args_policy(
            {"drop_database": {"filter": ArgumentSpec(forbid=("",))}}
        )
        engine = Engine(policy, audit_logger=AuditLogger(sink))
        decision = engine.evaluate(
            tool_name="drop_database",
            action="delete",
            environment="production",
            data_class="restricted",
            agent_id="release-bot",
            arguments={"filter": ""},
        )
        assert decision.decision == "deny"
        assert decision.reason_code == "deny_argument_policy"
        entries = sink.query()
        assert len(entries) == 1
        assert entries[0].decision == "deny"
        assert entries[0].reason_code == "deny_argument_policy"

    def test_argument_policy_deny_respects_dry_run(self, tmp_path):
        from agent_tooltrust.engine.argument_policy import ArgumentSpec

        sink = JsonlSink(str(tmp_path / "audit.jsonl"))
        policy = _policy_with_args_policy(
            {"drop_database": {"filter": ArgumentSpec(forbid=("",))}}
        )
        engine = Engine(policy, dry_run=True, audit_logger=AuditLogger(sink))
        decision = engine.evaluate(
            tool_name="drop_database",
            action="delete",
            environment="production",
            data_class="restricted",
            agent_id="release-bot",
            arguments={"filter": ""},
        )
        assert decision.decision == "allow"
        assert decision.dry_run is True
        entries = sink.query()
        assert len(entries) == 1
        assert entries[0].decision == "deny"
        assert entries[0].reason_code == "deny_argument_policy"

    def test_obligation_failure_deny_is_audited(self, tmp_path):
        sink = JsonlSink(str(tmp_path / "audit.jsonl"))
        engine = Engine(
            _policy_with_obligation(("no_such_obligation",)),
            audit_logger=AuditLogger(sink),
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
        entries = sink.query()
        assert len(entries) == 1
        assert entries[0].decision == "deny"

    def test_obligation_failure_deny_respects_dry_run(self, tmp_path):
        sink = JsonlSink(str(tmp_path / "audit.jsonl"))
        engine = Engine(
            _policy_with_obligation(("no_such_obligation",)),
            dry_run=True,
            audit_logger=AuditLogger(sink),
        )
        decision = engine.evaluate(
            tool_name="drop_database",
            action="delete",
            environment="production",
            data_class="restricted",
            agent_id="release-bot",
        )
        assert decision.decision == "allow"
        assert decision.dry_run is True
        entries = sink.query()
        assert len(entries) == 1
        assert entries[0].decision == "deny"
