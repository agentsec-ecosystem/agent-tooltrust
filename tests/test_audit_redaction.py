"""Tests for audit argument redaction."""

from __future__ import annotations

from agent_tooltrust.audit.redact import redact_arguments


class TestRedactArguments:
    def test_none_returns_none(self) -> None:
        result, redacted = redact_arguments(None)
        assert result is None
        assert redacted is False

    def test_empty_dict_no_redaction(self) -> None:
        result, redacted = redact_arguments({})
        assert result == {}
        assert redacted is False

    def test_default_sensitive_keys(self) -> None:
        args = {"user": "alice", "password": "s3cret"}
        result, redacted = redact_arguments(args)
        assert redacted is True
        assert result["password"] == "***REDACTED***"  # noqa: S105
        assert result["user"] == "alice"

    def test_case_insensitive_matching(self) -> None:
        args = {"ApiKey": "abc123", "API_SECRET": "xyz"}
        result, redacted = redact_arguments(args)
        assert redacted is True
        assert result["ApiKey"] == "***REDACTED***"
        assert result["API_SECRET"] == "***REDACTED***"  # noqa: S105

    def test_extra_keys_override(self) -> None:
        args = {"username": "alice", "path": "/secret/file"}
        result, redacted = redact_arguments(args, extra_keys={"path"})
        assert redacted is True
        assert result["path"] == "***REDACTED***"
        assert result["username"] == "alice"

    def test_nested_dict_redaction(self) -> None:
        args = {"connection": {"host": "db.example.com", "password": "hunter2"}}
        result, redacted = redact_arguments(args)
        assert redacted is True
        assert result["connection"]["password"] == "***REDACTED***"  # noqa: S105
        assert result["connection"]["host"] == "db.example.com"

    def test_list_of_dicts_redaction(self) -> None:
        args = {"items": [{"name": "ok", "token": "leet"}, {"name": "also_ok"}]}
        result, redacted = redact_arguments(args)
        assert redacted is True
        assert result["items"][0]["token"] == "***REDACTED***"  # noqa: S105
        assert result["items"][1]["name"] == "also_ok"

    def test_no_sensitive_keys_no_change(self) -> None:
        args = {"query": "SELECT 1", "limit": 10}
        result, redacted = redact_arguments(args)
        assert redacted is False
        assert result is args

    def test_args_unmodified_when_no_redaction(self) -> None:
        args = {"query": "SELECT 1"}
        result, _ = redact_arguments(args)
        assert result is args

    def test_deeply_nested_list(self) -> None:
        args = {"root": [{"level1": {"level2": {"secret": "buried"}}}]}
        result, redacted = redact_arguments(args)
        assert redacted is True
        assert result["root"][0]["level1"]["level2"]["secret"] == "***REDACTED***"  # noqa: S105


class TestRedactIntegration:
    def test_logger_redacts_arguments(self) -> None:
        from agent_tooltrust.audit.logger import AuditLogger
        from agent_tooltrust.audit.sink import AuditSink
        from agent_tooltrust.engine.engine import Engine
        from agent_tooltrust.policy.models import default_policy

        class MemorySink(AuditSink):
            def __init__(self) -> None:
                self.entries: list = []
            def write(self, entry: object) -> None:
                self.entries.append(entry)
            def query(self, session_id: str | None = None) -> list:
                return list(self.entries)

        sink = MemorySink()
        logger = AuditLogger(sink=sink)

        engine = Engine(default_policy("balanced"))
        from agent_tooltrust.engine.normalize import normalize

        call = normalize(
            tool="query_logs",
            action="read",
            environment="staging",
            data_class="internal",
            agent_id="debug-bot",
            arguments={"query": "SELECT 1", "token": "should_be_redacted"},
        )
        decision = engine.evaluate("query_logs", "read", "staging", "internal", "debug-bot")
        logger.log(decision, call)
        entry = sink.entries[0]
        assert entry.arguments["token"] == "***REDACTED***"  # noqa: S105
        assert entry.arguments["query"] == "SELECT 1"
        assert entry.redacted is True

    def test_logger_no_redaction_needed(self) -> None:
        from agent_tooltrust.audit.logger import AuditLogger
        from agent_tooltrust.audit.sink import AuditSink
        from agent_tooltrust.engine.engine import Engine
        from agent_tooltrust.policy.models import default_policy

        class MemorySink(AuditSink):
            def __init__(self) -> None:
                self.entries: list = []
            def write(self, entry: object) -> None:
                self.entries.append(entry)
            def query(self, session_id: str | None = None) -> list:
                return list(self.entries)

        sink = MemorySink()
        logger = AuditLogger(sink=sink)

        engine = Engine(default_policy("balanced"))
        from agent_tooltrust.engine.normalize import normalize

        call = normalize(
            tool="query_logs",
            action="read",
            environment="staging",
            data_class="internal",
            agent_id="debug-bot",
            arguments={"query": "SELECT 1"},
        )
        decision = engine.evaluate("query_logs", "read", "staging", "internal", "debug-bot")
        logger.log(decision, call)
        entry = sink.entries[0]
        assert entry.redacted is False
        assert entry.arguments["query"] == "SELECT 1"
