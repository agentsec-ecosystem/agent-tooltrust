"""Tests for M3 sinks — JSONL, SQLite, Postgres — and the AuditLogger facade.

Covers M3.3/M3.4/M3.5/M3.6 (#25-28, F-30/F-33): each sink writes and queries,
rotates, survives write failures without raising, and the facade dispatches to
a configured sink while never letting a persistence failure reach the caller.
"""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from agent_tooltrust.audit.logger import AuditLogger, build_sink, sink_from_config
from agent_tooltrust.audit.models import AuditEntry
from agent_tooltrust.audit.sink import AuditSink
from agent_tooltrust.audit.sinks.jsonl import JsonlSink
from agent_tooltrust.audit.sinks.postgres import PostgresSink
from agent_tooltrust.audit.sinks.sqlite import SqliteSink
from agent_tooltrust.engine.engine import Engine
from agent_tooltrust.engine.normalize import normalize
from agent_tooltrust.policy.models import default_policy
from agent_tooltrust.policy.schema import AuditConfig


def _unchained(entry: AuditEntry) -> AuditEntry:
    """Drop the tamper-chain fields so a round-tripped entry compares equal.

    Sinks persist ``chain_hash``/``prev_hash`` at write time (see
    ``audit.tamper_proof``), so a queried entry legitimately carries them
    even though the fixture was constructed without them. Content equality
    is what these round-trip tests care about.
    """
    return replace(entry, chain_hash=None, prev_hash=None)


@pytest.fixture
def entry() -> AuditEntry:
    engine = Engine(default_policy("balanced"))
    decision = engine.evaluate(
        tool_name="deploy_service",
        action="deploy",
        environment="production",
        data_class="restricted",
        agent_id="dev-eng",
    )
    call = normalize(
        tool="deploy_service",
        action="deploy",
        environment="production",
        data_class="restricted",
        agent_id="dev-eng",
        agent_class="engineer",
        session_id="sess_1",
    )
    return AuditEntry.from_decision(decision, call)


@pytest.fixture
def other_entry(entry: AuditEntry) -> AuditEntry:
    engine = Engine(default_policy("balanced"))
    decision = engine.evaluate(
        tool_name="query_logs",
        action="read",
        environment="staging",
        data_class="internal",
        agent_id="dev-eng",
    )
    call = normalize(
        tool="query_logs",
        action="read",
        environment="staging",
        data_class="internal",
        agent_id="dev-eng",
        agent_class="engineer",
        session_id="sess_2",
    )
    return AuditEntry.from_decision(decision, call)


class TestJsonlSink:
    def test_write_and_query(self, tmp_path, entry, other_entry):
        sink = JsonlSink(tmp_path / "audit.jsonl")
        sink.write(entry)
        sink.write(other_entry)
        assert [_unchained(e) for e in sink.query("sess_1")] == [entry]
        assert [_unchained(e) for e in sink.query("sess_2")] == [other_entry]
        assert len(sink.query()) == 2

    def test_file_contains_one_json_line_per_entry(self, tmp_path, entry):
        sink = JsonlSink(tmp_path / "audit.jsonl")
        sink.write(entry)
        sink.write(entry)
        lines = (tmp_path / "audit.jsonl").read_text().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["tool"] == "deploy_service"

    def test_rotation_creates_archive(self, tmp_path, entry):
        sink = JsonlSink(tmp_path / "audit.jsonl", max_bytes=10)
        sink.write(entry)
        sink.write(entry)
        assert (tmp_path / "audit.jsonl.1").exists()
        main = json.loads((tmp_path / "audit.jsonl").read_text().splitlines()[0])
        assert main["tool"] == "deploy_service"

    def test_query_missing_file_returns_empty(self, tmp_path):
        assert JsonlSink(tmp_path / "nope.jsonl").query() == []

    def test_write_failure_does_not_raise(self, tmp_path, entry, capsys):
        sink = JsonlSink(tmp_path / "audit.jsonl")
        sink._path = Path("/nonexistent-dir-that-does-not-exist/audit.jsonl")
        sink.write(entry)  # must not raise
        assert "write failed" in capsys.readouterr().err

    def test_creates_parent_directories(self, tmp_path, entry):
        sink = JsonlSink(tmp_path / "deep" / "nested" / "audit.jsonl")
        sink.write(entry)
        assert (tmp_path / "deep" / "nested" / "audit.jsonl").exists()

    def test_ignores_corrupt_lines(self, tmp_path, entry):
        path = tmp_path / "audit.jsonl"
        path.write_text("not json\n")
        sink = JsonlSink(path)
        sink.write(entry)
        assert [_unchained(e) for e in sink.query()] == [entry]


class TestSqliteSink:
    def test_write_and_query_by_session(self, tmp_path, entry, other_entry):
        sink = SqliteSink(tmp_path / "audit.db")
        sink.write(entry)
        sink.write(other_entry)
        assert [_unchained(e) for e in sink.query("sess_1")] == [entry]
        assert len(sink.query()) == 2

    def test_table_created_on_first_write(self, tmp_path, entry):
        sink = SqliteSink(tmp_path / "audit.db")
        sink.write(entry)
        import sqlite3

        conn = sqlite3.connect(tmp_path / "audit.db")
        names = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        assert "audit_entries" in names

    def test_query_empty_db(self, tmp_path):
        assert SqliteSink(tmp_path / "audit.db").query() == []
        assert SqliteSink(tmp_path / "audit.db").query("sess_1") == []

    def test_write_and_query_round_trip(self, tmp_path, entry):
        sink = SqliteSink(tmp_path / "audit.db")
        sink.write(entry)
        assert _unchained(sink.query("sess_1")[0]) == entry


class TestSinkConfig:
    def test_build_sink_jsonl(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        sink = build_sink(AuditConfig(sink="jsonl"))
        assert isinstance(sink, JsonlSink)

    def test_build_sink_sqlite(self, tmp_path):
        sink = build_sink(AuditConfig(sink="sqlite", path=str(tmp_path / "x.db")))
        assert isinstance(sink, SqliteSink)

    def test_build_sink_postgres(self):
        sink = build_sink(AuditConfig(sink="postgres", postgres_url="postgresql://u@h/db"))
        assert isinstance(sink, PostgresSink)

    def test_build_sink_postgres_missing_url_raises(self):
        with pytest.raises(ValueError):
            build_sink(AuditConfig(sink="postgres"))

    def test_sink_from_config_raw_dict(self, tmp_path):
        sink = sink_from_config({"sink": "sqlite", "path": str(tmp_path / "x2.db")})
        assert isinstance(sink, SqliteSink)

    def test_sink_from_config_empty_defaults_to_jsonl(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        sink = sink_from_config(None)
        assert isinstance(sink, JsonlSink)

    def test_build_sink_unknown_raises(self):
        with pytest.raises(ValueError):
            build_sink(AuditConfig(sink="mongo"))  # type: ignore[arg-type]


class TestPostgresSink:
    def test_write_falls_back_when_no_pool(self, tmp_path, entry, monkeypatch):
        sink = PostgresSink("postgresql://u@h/db", fallback_path=str(tmp_path / "fb.jsonl"))
        sink._pool = None
        sink._ensure_runtime = lambda: None  # type: ignore[method-assign]
        sink.write(entry)
        assert [_unchained(e) for e in sink._fallback.query()] == [entry]

    def test_require_asyncpg_raises_when_missing(self, monkeypatch):

        monkeypatch.setattr(
            "agent_tooltrust.audit.sinks.postgres.importlib.util.find_spec",
            lambda _name: None,
        )
        from agent_tooltrust.audit.sinks.postgres import _require_asyncpg

        with pytest.raises(ImportError, match=r"\[postgres\]"):
            _require_asyncpg()

    def test_write_failure_logs_and_falls_back(self, tmp_path, entry, capsys):
        sink = PostgresSink("postgresql://u@h/db", fallback_path=str(tmp_path / "fb.jsonl"))
        sink._pool = object()
        sink._do_write = lambda e: (_ for _ in ()).throw(RuntimeError("conn refused"))  # type: ignore[method-assign]
        sink.write(entry)
        captured = capsys.readouterr()
        assert "write failed" in captured.err
        assert [_unchained(e) for e in sink._fallback.query()] == [entry]

    def test_query_failure_falls_back(self, tmp_path, entry, capsys):
        sink = PostgresSink("postgresql://u@h/db", fallback_path=str(tmp_path / "fb.jsonl"))
        sink.write(entry)  # goes to fallback (no pool)
        sink._pool = object()
        sink._do_query = lambda s: (_ for _ in ()).throw(RuntimeError("conn refused"))  # type: ignore[method-assign]
        assert [_unchained(e) for e in sink.query()] == [entry]
        assert "query failed" in capsys.readouterr().err

    def test_write_with_pool_runs_insert(self, tmp_path, entry, monkeypatch):

        sink = PostgresSink("postgresql://u@h/db", fallback_path=str(tmp_path / "fb.jsonl"))
        calls = {}

        class FakeConn:
            def __init__(self):
                self.columns = {
                    "session_id",
                    "call_id",
                    "timestamp",
                    "tool",
                    "tool_category",
                    "action",
                    "action_class",
                    "environment",
                    "data_class",
                    "agent_id",
                    "agent_class",
                    "decision",
                    "criticality",
                    "reason_code",
                    "explanation",
                    "factors",
                    "policy_version",
                    "dry_run",
                    "escalation_id",
                    "approver",
                    "chain_hash",
                    "prev_hash",
                }

            async def execute(self, sql, *params):
                calls.setdefault(sql, []).append(params)

            async def fetchrow(self, sql, *params):
                if sql.lstrip().upper().startswith("SELECT CHAIN_HASH"):
                    return None
                return _Record(self.columns)

        class _Record:
            def __init__(self, columns):
                self._columns = columns

            def keys(self):
                return self._columns

        class FakePool:
            def acquire(self):
                return _AcquireContext(FakeConn())

        async def fake_open_pool():
            return FakePool()

        monkeypatch.setattr(sink, "_open_pool", fake_open_pool)
        sink._ensure_runtime()
        assert sink._pool is not None
        sink.write(entry)
        assert sink._fallback.query() == []
        assert any(
            entry.session_id in (params or ())
            for param_lists in calls.values()
            for params in param_lists
        )
        assert sink._loop is not None
        sink._loop.call_soon_threadsafe(sink._loop.stop)

    def test_query_with_pool_returns_entries(self, tmp_path, entry, monkeypatch):

        sink = PostgresSink("postgresql://u@h/db", fallback_path=str(tmp_path / "fb.jsonl"))

        class FakeConn:
            async def fetch(self, sql, *params):
                row = {
                    "session_id": "sess_1",
                    "timestamp": entry.timestamp,
                    "tool": entry.tool,
                    "tool_category": entry.tool_category,
                    "action": entry.action,
                    "action_class": entry.action_class,
                    "environment": entry.environment,
                    "data_class": entry.data_class,
                    "agent_id": entry.agent_id,
                    "agent_class": entry.agent_class,
                    "decision": entry.decision,
                    "criticality": entry.criticality,
                    "reason_code": entry.reason_code,
                    "explanation": entry.explanation,
                    "factors": [
                        {"dimension": "environment", "value": "production", "contribution": 0.7}
                    ],
                    "policy_version": entry.policy_version,
                    "dry_run": False,
                    "escalation_id": None,
                    "approver": None,
                }
                return [row]

        class FakePool:
            def acquire(self):
                return _AcquireContext(FakeConn())

        async def fake_open_pool():
            return FakePool()

        monkeypatch.setattr(sink, "_open_pool", fake_open_pool)
        sink._ensure_runtime()
        results = sink.query("sess_1")
        assert len(results) == 1
        assert results[0].session_id == "sess_1"
        assert results[0].factors[0].dimension == "environment"
        assert sink._loop is not None
        sink._loop.call_soon_threadsafe(sink._loop.stop)

    def test_row_to_entry_parses_string_factors(self, entry):
        from agent_tooltrust.audit.sinks.postgres import _row_to_entry

        row = {
            "session_id": "sess_1",
            "timestamp": entry.timestamp,
            "tool": entry.tool,
            "tool_category": None,
            "action": entry.action,
            "action_class": None,
            "environment": entry.environment,
            "data_class": entry.data_class,
            "agent_id": entry.agent_id,
            "agent_class": None,
            "decision": entry.decision,
            "criticality": entry.criticality,
            "reason_code": entry.reason_code,
            "explanation": entry.explanation,
            "factors": '[{"dimension": "environment", "value": "production", "contribution": 0.7}]',
            "policy_version": entry.policy_version,
            "dry_run": True,
            "escalation_id": None,
            "approver": None,
        }
        parsed = _row_to_entry(row)
        assert parsed.dry_run is True
        assert parsed.factors[0].dimension == "environment"


class _AcquireContext:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *exc):
        return None


class TestAuditLogger:
    class BoomSink(AuditSink):
        def write(self, entry):  # type: ignore[override]
            raise OSError("disk full")

        def query(self, session_id=None):
            return []

    def test_log_never_raises_on_sink_failure(self, entry, capsys):
        logger = AuditLogger(TestAuditLogger.BoomSink())
        result = logger.log(entry_with_decision(), make_call())
        assert "log failed" in capsys.readouterr().err
        assert isinstance(result, AuditEntry)

    def test_log_returns_entry(self, entry):
        logger = AuditLogger(DevNullSink())
        result = logger.log(entry_with_decision(), make_call())
        assert result.tool == "deploy_service"

    def test_query_delegates(self):
        sink = DevNullSink()
        logger = AuditLogger(sink)
        assert logger.query("sess_1") == []

    def test_default_sink_is_jsonl(self):
        assert isinstance(AuditLogger().sink, JsonlSink)

    def test_session_override_logged(self):
        sink = DevNullSink()
        logger = AuditLogger(sink)
        logger.log(entry_with_decision(), make_call(), session_id="override")
        assert sink.last is not None
        assert sink.last.session_id == "override"


class DevNullSink(AuditSink):
    def __init__(self) -> None:
        self.last = None

    def write(self, entry):  # type: ignore[override]
        self.last = entry

    def query(self, session_id=None):
        return []


def entry_with_decision():
    engine = Engine(default_policy("balanced"))
    decision = engine.evaluate(
        tool_name="deploy_service",
        action="deploy",
        environment="production",
        data_class="restricted",
        agent_id="dev-eng",
    )
    return decision


def make_call():
    call = normalize(
        tool="deploy_service",
        action="deploy",
        environment="production",
        data_class="restricted",
        agent_id="dev-eng",
        agent_class="engineer",
        session_id="sess_1",
    )
    return call
