"""Tests for the ``tooltrust audit`` CLI (M3.8).

Issue #24 (F-32). Covers show/query/export subcommands, json/csv output,
filters, and the ``--sink``/``--path``/``--url`` option plumbing. The CLI
writes to stdout, so each test captures stdout via capsys and seeds a JSONL
or SQLite sink by writing entries with the real sinks first.
"""

import json

import pytest

from agent_tooltrust.audit.models import AuditEntry
from agent_tooltrust.audit.sinks.jsonl import JsonlSink
from agent_tooltrust.audit.sinks.sqlite import SqliteSink
from agent_tooltrust.cli.audit import _build_sink
from agent_tooltrust.engine.engine import Engine
from agent_tooltrust.engine.normalize import normalize
from agent_tooltrust.policy.models import default_policy


def _entry(agent_id: str = "dev-eng", session_id: str = "sess_1") -> AuditEntry:
    engine = Engine(default_policy("balanced"))
    decision = engine.evaluate(
        tool_name="deploy_service",
        action="deploy",
        environment="production",
        data_class="restricted",
        agent_id=agent_id,
    )
    call = normalize(
        tool="deploy_service",
        action="deploy",
        environment="production",
        data_class="restricted",
        agent_id=agent_id,
        session_id=session_id,
    )
    return AuditEntry.from_decision(decision, call, session_id=session_id)


def _seed_jsonl(path) -> None:
    sink = JsonlSink(path)
    sink.write(_entry(agent_id="dev-eng", session_id="sess_1"))
    sink.write(_entry(agent_id="sec-ops", session_id="sess_2"))


def _seed_sqlite(path) -> None:
    sink = SqliteSink(path)
    sink.write(_entry(agent_id="dev-eng", session_id="sess_1"))
    sink.write(_entry(agent_id="sec-ops", session_id="sess_2"))


def _run(args, capsys, exit_code: int = 0):
    import argparse

    from agent_tooltrust.cli.audit import add_parser

    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers()
    add_parser(sub)
    if exit_code:
        with pytest.raises(SystemExit) as exc:
            ns = parser.parse_args(args)
            ns.func(ns)
        assert exc.value.code == exit_code
    else:
        ns = parser.parse_args(args)
        ns.func(ns)
    return capsys.readouterr()


class TestAuditShow:
    def test_show_json_jsonl(self, tmp_path, capsys):
        path = str(tmp_path / "audit.jsonl")
        _seed_jsonl(path)
        out = _run(["audit", "show", "--session", "sess_1", "--path", path], capsys).out
        rows = json.loads(out)
        assert isinstance(rows, list)
        assert len(rows) == 1
        assert rows[0]["session_id"] == "sess_1"
        assert rows[0]["tool"] == "deploy_service"

    def test_show_csv_jsonl(self, tmp_path, capsys):
        path = str(tmp_path / "audit.jsonl")
        _seed_jsonl(path)
        out = _run(
            ["audit", "show", "--session", "sess_1", "--path", path, "--format", "csv"], capsys
        ).out
        lines = out.strip().splitlines()
        assert lines[0].startswith("session_id,timestamp,tool")
        assert lines[1].startswith("sess_1,")

    def test_show_sqlite(self, tmp_path, capsys):
        path = str(tmp_path / "audit.db")
        _seed_sqlite(path)
        out = _run(
            ["audit", "show", "--session", "sess_1", "--sink", "sqlite", "--path", path], capsys
        ).out
        rows = json.loads(out)
        assert len(rows) == 1
        assert rows[0]["session_id"] == "sess_1"

    def test_show_empty_session(self, tmp_path, capsys):
        path = str(tmp_path / "audit.jsonl")
        _seed_jsonl(path)
        out = _run(["audit", "show", "--session", "nope", "--path", path], capsys).out
        assert json.loads(out) == []

    def test_show_requires_session(self, tmp_path, capsys):
        path = str(tmp_path / "audit.jsonl")
        _run(["audit", "show", "--path", path], capsys, exit_code=2)


class TestAuditQuery:
    def test_query_all(self, tmp_path, capsys):
        path = str(tmp_path / "audit.jsonl")
        _seed_jsonl(path)
        out = _run(["audit", "query", "--path", path], capsys).out
        assert len(json.loads(out)) == 2

    def test_query_filter_decision(self, tmp_path, capsys):
        path = str(tmp_path / "audit.jsonl")
        _seed_jsonl(path)
        out = _run(["audit", "query", "--path", path, "--decision", "escalate"], capsys).out
        rows = json.loads(out)
        assert rows and all(r["decision"] == "escalate" for r in rows)

    def test_query_filter_agent(self, tmp_path, capsys):
        path = str(tmp_path / "audit.jsonl")
        _seed_jsonl(path)
        out = _run(["audit", "query", "--path", path, "--agent", "sec-ops"], capsys).out
        rows = json.loads(out)
        assert len(rows) == 1
        assert rows[0]["agent_id"] == "sec-ops"

    def test_query_filter_session(self, tmp_path, capsys):
        path = str(tmp_path / "audit.jsonl")
        _seed_jsonl(path)
        out = _run(["audit", "query", "--path", path, "--session", "sess_2"], capsys).out
        rows = json.loads(out)
        assert len(rows) == 1
        assert rows[0]["session_id"] == "sess_2"

    def test_query_filter_since(self, tmp_path, capsys):
        path = str(tmp_path / "audit.jsonl")
        _seed_jsonl(path)
        rows = JsonlSink(path).query()
        earliest = min(r.timestamp for r in rows)
        out = _run(["audit", "query", "--path", path, "--since", earliest], capsys).out
        assert len(json.loads(out)) == 2
        out = _run(
            ["audit", "query", "--path", path, "--since", "9999-12-31T00:00:00+00:00"], capsys
        ).out
        assert json.loads(out) == []

    def test_query_csv(self, tmp_path, capsys):
        path = str(tmp_path / "audit.jsonl")
        _seed_jsonl(path)
        out = _run(["audit", "query", "--path", path, "--format", "csv"], capsys).out
        lines = out.strip().splitlines()
        assert lines[0].startswith("session_id,")
        assert len(lines) == 3


class TestAuditExport:
    def test_export_csv_default(self, tmp_path, capsys):
        path = str(tmp_path / "audit.jsonl")
        _seed_jsonl(path)
        out = _run(["audit", "export", "--path", path], capsys).out
        lines = out.strip().splitlines()
        assert lines[0].startswith("session_id,")
        assert len(lines) == 3

    def test_export_json(self, tmp_path, capsys):
        path = str(tmp_path / "audit.jsonl")
        _seed_jsonl(path)
        out = _run(["audit", "export", "--path", path, "--format", "json"], capsys).out
        assert len(json.loads(out)) == 2

    def test_export_session(self, tmp_path, capsys):
        path = str(tmp_path / "audit.jsonl")
        _seed_jsonl(path)
        out = _run(["audit", "export", "--path", path, "--session", "sess_1"], capsys).out
        lines = out.strip().splitlines()
        assert len(lines) == 2
        assert lines[1].startswith("sess_1,")


class TestAuditSinkOptions:
    def test_build_sink_jsonl_default(self, tmp_path):
        sink = _build_sink(argparse_namespace("jsonl", None, None))
        assert isinstance(sink, JsonlSink)

    def test_build_sink_sqlite_path(self, tmp_path):
        sink = _build_sink(argparse_namespace("sqlite", str(tmp_path / "x.db"), None))
        assert isinstance(sink, SqliteSink)
        assert sink.path == tmp_path / "x.db"

    def test_build_sink_postgres_requires_url(self, tmp_path):
        from agent_tooltrust.cli.errors import CliError

        with pytest.raises(CliError):
            _build_sink(argparse_namespace("postgres", None, None))

    def test_build_sink_postgres_url(self, tmp_path):
        sink = _build_sink(argparse_namespace("postgres", None, "postgresql://u:p@h/db"))
        assert type(sink).__name__ == "PostgresSink"


def argparse_namespace(sink, path, url):
    import argparse

    ns = argparse.Namespace(sink=sink, path=path, url=url)
    return ns
