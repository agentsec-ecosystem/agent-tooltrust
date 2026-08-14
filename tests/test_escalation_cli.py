"""Tests for M3 Task 2 (#85, F-90) — the ``tooltrust escalation`` CLI.

Covers the human approval round-trip via the CLI: list pending, approve with
an approver, deny with a reason, persistence across invocations, and failure
on unknown/already-resolved ids.
"""

from __future__ import annotations

import argparse

import pytest

from agent_tooltrust.cli.errors import CliError
from agent_tooltrust.cli.escalation import (
    _approve,
    _approver,
    _deny,
    _list,
    add_parser,
)
from agent_tooltrust.engine.escalation import EscalationManager, EscalationStatus
from agent_tooltrust.types import NormalizedCall


def _ns(**kwargs) -> argparse.Namespace:
    defaults = {
        "file": "~/tooltrust-test-escalations.json",
        "approver": "ops@example.com",
        "reason": "",
        "show_all": False,
        "id": "esc_0000000000000000",
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def _seed(store: str, *, agent: str = "dev-eng", tool: str = "deploy_service") -> str:
    mgr = EscalationManager()
    call = NormalizedCall(
        tool=tool,
        tool_category="cloud",
        action="deploy",
        action_class="write",
        environment="production",
        data_class="restricted",
        agent_id=agent,
        agent_class="engineer",
    )
    esc = mgr.create(call, reason="requires approval")
    mgr.save(store)
    return esc.escalation_id


class TestList:
    def test_empty_list(self, tmp_path):
        store = str(tmp_path / "esc.json")
        assert _list(_ns(file=store)) == 0

    def test_pending_listed(self, tmp_path):
        store = str(tmp_path / "esc.json")
        esc_id = _seed(store)
        _list(_ns(file=store))
        mgr = EscalationManager.load(store)
        assert mgr.records[esc_id].status == EscalationStatus.PENDING


class TestApprove:
    def test_approve_round_trip(self, tmp_path):
        store = str(tmp_path / "esc.json")
        esc_id = _seed(store)
        assert _approve(_ns(file=store, id=esc_id)) == 0
        mgr = EscalationManager.load(store)
        record = mgr.records[esc_id]
        assert record.status == EscalationStatus.APPROVED
        assert record.approver == "ops@example.com"

    def test_approve_unknown_id_raises(self, tmp_path):
        store = str(tmp_path / "esc.json")
        _seed(store)
        with pytest.raises(CliError):
            _approve(_ns(file=store))

    def test_approve_twice_raises(self, tmp_path):
        store = str(tmp_path / "esc.json")
        esc_id = _seed(store)
        _approve(_ns(file=store, id=esc_id))
        with pytest.raises(CliError):
            _approve(_ns(file=store, id=esc_id))


class TestDeny:
    def test_deny_round_trip_records_reason(self, tmp_path):
        store = str(tmp_path / "esc.json")
        esc_id = _seed(store)
        assert _deny(_ns(file=store, id=esc_id, reason="not approved")) == 0
        mgr = EscalationManager.load(store)
        record = mgr.records[esc_id]
        assert record.status == EscalationStatus.DENIED
        assert record.approver == "ops@example.com"
        assert record.denied_reason == "not approved"

    def test_deny_unknown_id_raises(self, tmp_path):
        store = str(tmp_path / "esc.json")
        _seed(store)
        with pytest.raises(CliError):
            _deny(_ns(file=store))


class TestApprover:
    def test_explicit_approver_used(self):
        assert _approver(_ns(approver="ops@example.com")) == "ops@example.com"

    def test_missing_approver_falls_back_to_getuser(self):
        name = _approver(_ns(approver=None))
        assert isinstance(name, str)
        assert name


class TestParser:
    def test_parser_registers_three_subcommands(self):
        parent = argparse.ArgumentParser()
        subs = parent.add_subparsers(dest="cmd")
        add_parser(subs)
        for cmd, extra in (("list", []), ("approve", ["id1"]), ("deny", ["id1"])):
            args = parent.parse_args(["escalation", cmd, *extra, "--file", "x"])
            assert args.escalation_command == cmd

    def test_parser_wires_funcs(self):
        parent = argparse.ArgumentParser()
        subs = parent.add_subparsers(dest="cmd")
        add_parser(subs)
        assert parent.parse_args(["escalation", "list", "--file", "x"]).func == _list
        assert parent.parse_args(["escalation", "approve", "id1", "--file", "x"]).func == _approve
        assert parent.parse_args(["escalation", "deny", "id1", "--file", "x"]).func == _deny


class TestListOutput:
    def test_list_shows_pending_records(self, tmp_path, capsys):
        store = str(tmp_path / "esc.json")
        esc_id = _seed(store)
        _list(_ns(file=store))
        out = capsys.readouterr().out
        assert esc_id in out
        assert "pending" in out

    def test_list_all_shows_approved(self, tmp_path, capsys):
        store = str(tmp_path / "esc.json")
        esc_id = _seed(store)
        _approve(_ns(file=store, id=esc_id))
        _list(_ns(file=store, show_all=True))
        out = capsys.readouterr().out
        assert "approved" in out
        assert "ops@example.com" in out

    def test_list_empty_prints_no_escalations(self, tmp_path, capsys):
        store = str(tmp_path / "esc.json")
        _list(_ns(file=store))
        assert "no escalations" in capsys.readouterr().out


class TestAuditIntegration:
    def test_approve_writes_audit_entry(self, tmp_path, monkeypatch):
        from agent_tooltrust.audit.sinks.jsonl import JsonlSink
        from agent_tooltrust.cli import escalation as escalation_cli

        audit_path = tmp_path / "audit.jsonl"
        monkeypatch.setattr(
            escalation_cli, "JsonlSink", lambda p: JsonlSink(str(audit_path))
        )
        store = str(tmp_path / "esc.json")
        esc_id = _seed(store)
        _approve(_ns(file=store, id=esc_id))
        entries = JsonlSink(str(audit_path)).query()
        assert len(entries) == 1
        assert entries[0].escalation_id == esc_id
        assert entries[0].decision == "allow"
        assert entries[0].approver == "ops@example.com"

    def test_deny_writes_audit_entry(self, tmp_path, monkeypatch):
        from agent_tooltrust.audit.sinks.jsonl import JsonlSink
        from agent_tooltrust.cli import escalation as escalation_cli

        audit_path = tmp_path / "audit.jsonl"
        monkeypatch.setattr(
            escalation_cli, "JsonlSink", lambda p: JsonlSink(str(audit_path))
        )
        store = str(tmp_path / "esc.json")
        esc_id = _seed(store)
        _deny(_ns(file=store, id=esc_id, reason="not now"))
        entries = JsonlSink(str(audit_path)).query()
        assert len(entries) == 1
        assert entries[0].escalation_id == esc_id
        assert entries[0].decision == "deny"
        assert entries[0].approver == "ops@example.com"
        assert entries[0].explanation == "not now"
