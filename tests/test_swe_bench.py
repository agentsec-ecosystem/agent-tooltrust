"""Tests for the SWE-bench ToolTrust integration."""

from __future__ import annotations

import json

import pytest

from agent_tooltrust.engine.engine import Engine
from agent_tooltrust.integrations.swe_bench import (
    SWEBenchGuard,
    SWEBenchTaskResult,
    SWEBenchToolMapper,
)
from agent_tooltrust.policy.models import default_policy


class TestSWEBenchToolMapper:
    def test_bash_read_maps_correctly(self) -> None:
        mapper = SWEBenchToolMapper()
        tool_name, action, _, _ = mapper.map("bash", "cat setup.py")
        assert tool_name == "bash"
        assert action == "read"

    def test_bash_write_maps_correctly(self) -> None:
        mapper = SWEBenchToolMapper()
        tool_name, action, _, _ = mapper.map("bash", "rm -rf build/ && pip install -e .")
        assert tool_name == "bash"
        assert action == "write"

    def test_bash_delete_maps_correctly(self) -> None:
        mapper = SWEBenchToolMapper()
        tool_name, action, _, _ = mapper.map("bash", "rm -rf /important/data")
        assert tool_name == "bash"
        assert action == "delete"

    def test_editor_view_maps_to_read(self) -> None:
        mapper = SWEBenchToolMapper()
        _, action, _, _ = mapper.map("str_replace_editor", "command:view,path:/src/main.py [1:50]")
        assert action == "read"

    def test_editor_insert_maps_to_write(self) -> None:
        mapper = SWEBenchToolMapper()
        insert_cmd = "command:insert,path:/src/main.py,text:new code"
        _, action, _, _ = mapper.map("str_replace_editor", insert_cmd)
        assert action == "write"

    def test_safe_command_not_destructive(self) -> None:
        mapper = SWEBenchToolMapper()
        assert not mapper.is_destructive("bash", "ls -la")
        assert not mapper.is_destructive("bash", "pytest tests/")
        assert not mapper.is_destructive("str_replace_editor", "command:view,path:foo.py")

    def test_destructive_commands_detected(self) -> None:
        mapper = SWEBenchToolMapper()
        assert mapper.is_destructive("bash", "rm -rf /")
        assert mapper.is_destructive("bash", "git push --force origin main")
        assert mapper.is_destructive("bash", ':(){ :|:& };:')


class TestSWEBenchGuard:
    @pytest.fixture
    def guard(self) -> SWEBenchGuard:
        engine = Engine(default_policy("balanced"))
        return SWEBenchGuard(engine, environment="swe_bench", data_class="public")

    def test_read_allowed(self, guard: SWEBenchGuard) -> None:
        result = guard.evaluate_tool_call("bash", "cat setup.py")
        assert result["decision"] == "allow" or result["decision"] == "audit"

    def test_destructive_denied(self, guard: SWEBenchGuard) -> None:
        result = guard.evaluate_tool_call("bash", "rm -rf /etc/important")
        expected = result.get("decision")
        assert expected in ("deny", "escalate", "audit")

    def test_git_force_push_denied(self, guard: SWEBenchGuard) -> None:
        result = guard.evaluate_tool_call("bash", "git push --force origin main")
        assert result["decision"] != "allow"

    def test_editor_edit_on_restricted_data_escalates(self) -> None:
        engine = Engine(default_policy("balanced"))
        guard = SWEBenchGuard(engine, environment="production", data_class="restricted")
        edit_cmd = "command:insert,path:/src/config.py,text:new config"
        result = guard.evaluate_tool_call("str_replace_editor", edit_cmd)
        expected = result.get("decision")
        assert expected in ("escalate", "audit", "deny")

    def test_task_trace_produces_report(self, guard: SWEBenchGuard) -> None:
        guard.start_task("test_task_1")
        guard.evaluate_tool_call("bash", "cat setup.py")
        guard.evaluate_tool_call("bash", "pip install pytest")
        guard.evaluate_tool_call("str_replace_editor", 'command:view,path:foo.py')
        result: SWEBenchTaskResult = guard.finish_task()

        assert result.task_id == "test_task_1"
        assert result.total_calls == 3
        assert len(result.decisions) == 3
        assert result.allowed_calls >= 0
        report = result.to_report()
        assert report["task_id"] == "test_task_1"
        assert report["total_calls"] == 3
        assert "decisions" in report

    def test_multiple_tasks_produce_separate_traces(self, guard: SWEBenchGuard) -> None:
        guard.start_task("task_a")
        guard.evaluate_tool_call("bash", "cat a.py")
        result_a = guard.finish_task()

        guard.start_task("task_b")
        guard.evaluate_tool_call("bash", "cat b.py")
        result_b = guard.finish_task()

        assert result_a.task_id == "task_a"
        assert result_b.task_id == "task_b"
        assert result_a.total_calls == 1
        assert result_b.total_calls == 1

    def test_guard_json_output(self, guard: SWEBenchGuard) -> None:
        guard.start_task("json_test")
        guard.evaluate_tool_call("bash", "cat setup.py")
        guard.evaluate_tool_call("bash", "pytest")
        result = guard.finish_task()
        report = result.to_report()
        json_str = json.dumps(report)
        assert "task_id" in json_str
        assert "total_calls" in json_str
