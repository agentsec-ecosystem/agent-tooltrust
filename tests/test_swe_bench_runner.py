"""Tests for the M23 SWE-bench integration (runner, policy, CLI)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_tooltrust.cli import main
from agent_tooltrust.engine.engine import Engine
from agent_tooltrust.integrations.swe_bench import (
    SWEBenchBenchmarkResult,
    SWEBenchGuard,
    SWEBenchRunner,
    SWEBenchTaskResult,
    SWEBenchToolMapper,
    swe_bench_policy,
)
from agent_tooltrust.policy.models import default_policy

FIXTURES = Path(__file__).parent / "fixtures" / "swe_bench_tasks.yaml"

TOTAL_CALLS = 32  # 7 + 6 + 7 + 5 + 7 across the five fixture tasks


def _engine(posture: str = "balanced") -> Engine:
    return Engine(swe_bench_policy(posture))


class TestSWEBenchToolMapper:
    def test_bash_read(self) -> None:
        tool_name, action, env, data = SWEBenchToolMapper().map("bash", "cat setup.py")
        assert (tool_name, action, env, data) == ("bash", "read", "swe_bench", "public")

    def test_bash_write_install(self) -> None:
        mapper = SWEBenchToolMapper()
        assert mapper.map("bash", "rm -rf build/ && pip install -e .")[1] == "write"

    def test_bash_delete_absolute(self) -> None:
        mapper = SWEBenchToolMapper()
        assert mapper.map("bash", "rm -rf /important/data")[1] == "delete"

    def test_bash_read_first_token(self) -> None:
        mapper = SWEBenchToolMapper()
        assert mapper.map("bash", "ls -la")[1] == "read"
        assert mapper.map("bash", "grep -rn foo src/")[1] == "read"
        assert mapper.map("bash", "cd /repo && cat setup.py")[1] == "read"
        assert mapper.map("bash", "sed -n '1,80p' file.py")[1] == "read"

    def test_bash_redirection_writes(self) -> None:
        mapper = SWEBenchToolMapper()
        assert mapper.map("bash", "echo hello > out.txt")[1] == "write"
        assert mapper.map("bash", "printf x >> log")[1] == "write"

    def test_git_subcommand_classification(self) -> None:
        mapper = SWEBenchToolMapper()
        assert mapper.map("bash", "git status")[1] == "read"
        assert mapper.map("bash", "git diff")[1] == "read"
        assert mapper.map("bash", "git log --oneline")[1] == "read"
        assert mapper.map("bash", "git commit -m fix")[1] == "write"
        assert mapper.map("bash", "git push origin main")[1] == "write"

    def test_unknown_command_is_conservative_write(self) -> None:
        mapper = SWEBenchToolMapper()
        assert mapper.map("bash", "some_obscure_tool --magic")[1] == "write"

    def test_unknown_tool_name_uses_shell_classifier(self) -> None:
        mapper = SWEBenchToolMapper()
        assert mapper.map("terminal", "cat file.py")[1] == "read"

    def test_editor_verbs(self) -> None:
        mapper = SWEBenchToolMapper()
        replace_cmd = "command:str_replace,path:foo.py,old:x,new:y"
        assert mapper.map("str_replace_editor", "command:view,path:foo.py [1:20]")[1] == "read"
        assert mapper.map("str_replace_editor", "command:open,path:foo.py")[1] == "read"
        assert mapper.map("str_replace_editor", "command:insert,path:foo.py,text:x")[1] == "write"
        assert mapper.map("str_replace_editor", replace_cmd)[1] == "write"
        assert mapper.map("str_replace_editor", "command:create,path:foo.py")[1] == "write"
        assert mapper.map("str_replace_editor", "command:undo_edit,path:foo.py")[1] == "write"
        assert mapper.map("str_replace_editor", "command:delete,path:foo.py")[1] == "delete"
        assert mapper.map("str_replace_editor", "garbage input")[1] == "write"

    def test_write_tool_is_write(self) -> None:
        mapper = SWEBenchToolMapper()
        assert mapper.map("write", "/repo/src/main.py\nprint('hi')")[1] == "write"

    def test_custom_environment_and_data_class(self) -> None:
        mapper = SWEBenchToolMapper(environment="production", data_class="restricted")
        assert mapper.map("bash", "cat x")[2:] == ("production", "restricted")

    def test_is_destructive_true(self) -> None:
        mapper = SWEBenchToolMapper()
        assert mapper.is_destructive("bash", "rm -rf /")
        assert mapper.is_destructive("bash", "rm -rf /var/lib/data")
        assert mapper.is_destructive("bash", "git push --force origin main")
        assert mapper.is_destructive("bash", "git clean -fd")
        assert mapper.is_destructive("bash", "git reset --hard HEAD~1")
        assert mapper.is_destructive("bash", ":(){ :|:& };:")
        assert mapper.is_destructive("bash", "mkfs.ext4 /dev/sda")
        assert mapper.is_destructive("bash", "dd if=/dev/zero of=/dev/sda")
        assert mapper.is_destructive("bash", "dropdb prod")

    def test_is_destructive_false(self) -> None:
        mapper = SWEBenchToolMapper()
        replace_cmd = "command:str_replace,path:foo.py,old:x,new:y"
        assert not mapper.is_destructive("bash", "ls -la")
        assert not mapper.is_destructive("bash", "pytest tests/")
        assert not mapper.is_destructive("bash", "rm -rf build/ && pip install -e .")
        assert not mapper.is_destructive("bash", "git status")
        assert not mapper.is_destructive("str_replace_editor", "command:view,path:foo.py")
        assert not mapper.is_destructive("str_replace_editor", replace_cmd)
        assert not mapper.is_destructive("write", "print('hello')")


class TestSWEBenchGuard:
    def test_standalone_evaluation_without_task(self) -> None:
        guard = SWEBenchGuard(Engine(default_policy("balanced")))
        result = guard.evaluate_tool_call("bash", "cat setup.py")
        assert result["decision"] in ("allow", "audit")
        assert result["tool"] == "bash"
        assert result["action"] == "read"
        assert "reason_code" in result
        assert guard.task_id is None

    def test_start_task_blank_raises(self) -> None:
        guard = SWEBenchGuard(_engine())
        with pytest.raises(ValueError):
            guard.start_task("   ")

    def test_finish_without_task_raises(self) -> None:
        guard = SWEBenchGuard(_engine())
        with pytest.raises(RuntimeError):
            guard.finish_task()

    def test_violation_flag_on_destructive_command(self) -> None:
        guard = SWEBenchGuard(_engine())
        result = guard.evaluate_tool_call("bash", "rm -rf /")
        assert result["destructive"] is True
        assert result["violation"] is True

    def test_trace_entry_fields(self) -> None:
        guard = SWEBenchGuard(_engine())
        guard.start_task("t1")
        entry = guard.evaluate_tool_call("str_replace_editor", "command:insert,path:a.py,text:x")
        assert entry["engine_tool"] == "write_file"
        assert entry["action"] == "write"
        assert entry["violation"] is False
        result = guard.finish_task()
        assert result.decisions[0] is entry

    def test_git_force_push_maps_to_force_push_tool(self) -> None:
        guard = SWEBenchGuard(_engine())
        entry = guard.evaluate_tool_call("bash", "git push --force origin main")
        assert entry["engine_tool"] == "force_push"
        assert entry["decision"] != "allow"

    def test_env_and_data_class_forwarded(self) -> None:
        guard = SWEBenchGuard(_engine(), environment="production", data_class="restricted")
        entry = guard.evaluate_tool_call("str_replace_editor", "command:insert,path:c.py,text:x")
        assert entry["decision"] in ("deny", "escalate", "audit")


class TestSWEBenchTaskResult:
    def test_properties_and_report(self) -> None:
        result = SWEBenchTaskResult(
            task_id="t",
            decisions=(
                {
                    "decision": "allow",
                    "tool": "bash",
                    "command": "a",
                    "action": "read",
                    "reason_code": "r1",
                },
                {
                    "decision": "deny",
                    "tool": "bash",
                    "command": "b",
                    "action": "delete",
                    "reason_code": "r2",
                    "violation": True,
                },
                {
                    "decision": "audit",
                    "tool": "bash",
                    "command": "c",
                    "action": "write",
                    "reason_code": "r3",
                },
            ),
        )
        assert result.total_calls == 3
        assert result.allowed_calls == 1
        assert len(result.violations) == 1
        report = result.to_report()
        assert report["task_id"] == "t"
        assert report["total_calls"] == 3
        assert report["allowed_calls"] == 1
        assert report["violations"][0]["decision"] == "deny"
        assert len(report["decisions"]) == 3
        assert json.loads(json.dumps(report))["task_id"] == "t"


class TestSWEBenchRunner:
    def test_run_task_returns_trace(self) -> None:
        runner = SWEBenchRunner(_engine())
        result = runner.run_task(
            "t1",
            [
                {"tool": "bash", "command": "cat a.py"},
                {"tool": "bash", "command": "python -m pytest tests/"},
            ],
        )
        assert isinstance(result, SWEBenchTaskResult)
        assert result.task_id == "t1"
        assert result.total_calls == 2

    def test_run_tasks_aggregates(self) -> None:
        runner = SWEBenchRunner(_engine())
        result = runner.run_tasks(
            [
                {"task_id": "a", "calls": [{"tool": "bash", "command": "cat a.py"}]},
                {"task_id": "b", "calls": [{"tool": "bash", "command": "cat b.py"}]},
            ]
        )
        assert isinstance(result, SWEBenchBenchmarkResult)
        assert result.total_tasks == 2
        assert result.tasks_completed == 2
        assert [r.task_id for r in result.results] == ["a", "b"]

    def test_fixture_five_tasks_all_complete(self) -> None:
        runner = SWEBenchRunner(_engine())
        result = runner.run_fixture(FIXTURES)
        assert result.total_tasks == 5
        assert result.tasks_completed == 5
        assert sum(r.total_calls for r in result.results) == TOTAL_CALLS
        assert result.violations_flagged == 2

    def test_fixture_probes_flagged(self) -> None:
        runner = SWEBenchRunner(_engine())
        result = runner.run_fixture(FIXTURES)
        flagged_commands = {
            v["command"]
            for task in result.results
            for v in task.violations
        }
        assert "git push --force origin main" in flagged_commands
        assert any(":(){" in command for command in flagged_commands)

    def test_fixture_returns_json_report(self) -> None:
        runner = SWEBenchRunner(_engine())
        report = runner.run_fixture(FIXTURES).to_report()
        assert report["total_tasks"] == 5
        assert len(report["tasks"]) == 5
        assert all(task["total_calls"] > 0 for task in report["tasks"])

    def test_fixture_missing_file_raises(self) -> None:
        runner = SWEBenchRunner(_engine())
        with pytest.raises(FileNotFoundError):
            runner.run_fixture(Path(__file__).parent / "fixtures" / "nope.yaml")

    def test_fixture_plain_list_schema(self, tmp_path: Path) -> None:
        fixture = tmp_path / "tasks.yaml"
        fixture.write_text(
            "- task_id: t1\n"
            "  calls:\n"
            '    - {tool: bash, command: "cat a.py"}\n'
        )
        runner = SWEBenchRunner(_engine())
        result = runner.run_fixture(fixture)
        assert result.total_tasks == 1
        assert result.results[0].task_id == "t1"


class TestSweBenchPolicy:
    def test_declares_swe_bench_environment(self) -> None:
        policy = swe_bench_policy("balanced")
        assert policy.environments["swe_bench"] == 0.0

    def test_inherits_balanced_rules(self) -> None:
        policy = swe_bench_policy("balanced")
        assert any(
            rule.decision == "deny"
            and rule.action == "delete"
            and rule.environment == "production"
            for rule in policy.rules
        )

    def test_strict_and_permissive(self) -> None:
        assert swe_bench_policy("strict").posture == "strict"
        assert swe_bench_policy("permissive").posture == "permissive"

    def test_invalid_posture_falls_back(self) -> None:
        assert swe_bench_policy("paranoid").posture == "balanced"


class TestSweBenchCli:
    def test_text_output_reports_five_tasks(self, capsys) -> None:
        rc = main(["swebench", "--fixtures", str(FIXTURES), "--posture", "balanced"])
        captured = capsys.readouterr()
        assert rc == 0
        assert "5/5 tasks completed" in captured.out
        assert "Task django__django-11099" in captured.out
        assert "VIOLATION" in captured.out

    def test_json_output(self, capsys) -> None:
        rc = main(["swebench", "--fixtures", str(FIXTURES), "--json"])
        captured = capsys.readouterr()
        assert rc == 0
        report = json.loads(captured.out)
        assert report["total_tasks"] == 5
        assert report["violations_flagged"] == 2

    def test_missing_fixture_exits_one(self, capsys) -> None:
        rc = main(["swebench", "--fixtures", "/nope/tasks.yaml"])
        captured = capsys.readouterr()
        assert rc == 1
        assert "fixtures file not found" in captured.err

    def test_malformed_fixture_exits_one(self, tmp_path: Path, capsys) -> None:
        bad = tmp_path / "bad.yaml"
        bad.write_text("tasks: [\n  {broken\n")
        rc = main(["swebench", "--fixtures", str(bad)])
        captured = capsys.readouterr()
        assert rc == 1
        assert "tooltrust: error:" in captured.err

    def test_policy_file_loaded(self, capsys) -> None:
        policy = Path("src/agent_tooltrust/policy/postures/balanced.yaml")
        rc = main(["swebench", "--fixtures", str(FIXTURES), "--policy", str(policy)])
        captured = capsys.readouterr()
        assert rc == 0
        assert "5/5 tasks completed" in captured.out

    def test_strict_posture_flags_more_violations(self, capsys) -> None:
        rc = main(["swebench", "--fixtures", str(FIXTURES), "--posture", "strict", "--json"])
        captured = capsys.readouterr()
        assert rc == 0
        report = json.loads(captured.out)
        assert report["violations_flagged"] > 2


class TestSweBenchGuardEngineToolMapping:
    def test_read_maps_to_read_file(self) -> None:
        guard = SWEBenchGuard(_engine())
        entry = guard.evaluate_tool_call("bash", "cat a.py")
        assert entry["engine_tool"] == "read_file"

    def test_git_commit_maps_to_commit_changes(self) -> None:
        guard = SWEBenchGuard(_engine())
        entry = guard.evaluate_tool_call("bash", "git commit -m fix")
        assert entry["engine_tool"] == "commit_changes"

    def test_git_push_maps_to_push_changes(self) -> None:
        guard = SWEBenchGuard(_engine())
        entry = guard.evaluate_tool_call("bash", "git push origin main")
        assert entry["engine_tool"] == "push_changes"

    def test_git_clone_maps_to_clone_repo(self) -> None:
        guard = SWEBenchGuard(_engine())
        entry = guard.evaluate_tool_call("bash", "git clone https://github.com/x/y")
        assert entry["engine_tool"] == "clone_repo"

    def test_grant_maps_to_assign_role(self) -> None:
        guard = SWEBenchGuard(_engine())
        assert guard._engine_tool("bash", "grant", "chmod 777 /etc/passwd") == "assign_role"
