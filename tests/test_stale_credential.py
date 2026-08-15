"""Tests for stale-credential audit classification."""

from __future__ import annotations

from agent_tooltrust.audit.logger import AuditLogger
from agent_tooltrust.audit.sink import AuditSink
from agent_tooltrust.engine.engine import Engine
from agent_tooltrust.engine.normalize import normalize
from agent_tooltrust.policy.models import default_policy


def test_credential_stale_status_on_entry() -> None:
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

    call = normalize(
        tool="query_logs", action="read", environment="staging",
        data_class="internal", agent_id="debug-bot",
    )
    decision = engine.evaluate("query_logs", "read", "staging", "internal", "debug-bot")
    logger.log(decision, call, credential_status="stale")
    entry = sink.entries[0]
    assert entry.credential_status == "stale"
    assert entry.decision == "allow"


def test_credential_defaults_to_none() -> None:
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

    call = normalize(
        tool="query_logs", action="read", environment="staging",
        data_class="internal", agent_id="debug-bot",
    )
    decision = engine.evaluate("query_logs", "read", "staging", "internal", "debug-bot")
    logger.log(decision, call)
    entry = sink.entries[0]
    assert entry.credential_status is None


def test_credential_queryable_in_audit() -> None:
    from agent_tooltrust.audit.models import AuditEntry

    entry = AuditEntry(
        session_id="s1", timestamp="2026-01-01T00:00:00",
        tool="query_logs", tool_category=None, action="read",
        action_class=None, environment="staging", data_class="internal",
        agent_id="bot1", agent_class=None,
        decision="allow", criticality="low", reason_code="ok", explanation="",
        credential_status="stale",
    )
    assert entry.credential_status == "stale"

    d = entry.to_dict()
    assert d.get("credential_status") == "stale"

    restored = AuditEntry.from_dict(d)
    assert restored.credential_status == "stale"
