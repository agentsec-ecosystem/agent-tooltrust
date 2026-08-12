"""CLI integration tests — all tooltrust subcommands."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "run", "tooltrust", *args],
        capture_output=True,
        text=True,
        timeout=10,
    )


class TestCLIIntegration:
    def test_help(self) -> None:
        result = _run("--help")
        assert result.returncode == 0
        assert "evaluate" in result.stdout
        assert "explain" in result.stdout
        assert "field-test" in result.stdout

    def test_version(self) -> None:
        result = _run("--version")
        assert result.returncode == 0

    def test_evaluate_allow(self) -> None:
        result = _run(
            "evaluate",
            "--tool", "query_logs",
            "--action", "read",
            "--env", "staging",
            "--data", "internal",
            "--agent", "debug-bot",
        )
        assert "ALLOW" in result.stdout
        assert result.returncode == 0

    def test_evaluate_deny_exit_code(self) -> None:
        result = _run(
            "evaluate",
            "--tool", "drop_database",
            "--action", "delete",
            "--env", "production",
            "--data", "customer_pii",
            "--agent", "bad-bot",
        )
        assert "DENY" in result.stdout
        assert result.returncode == 2

    def test_evaluate_json_format(self) -> None:
        result = _run(
            "evaluate",
            "--tool", "query_logs",
            "--action", "read",
            "--env", "staging",
            "--data", "internal",
            "--agent", "debug-bot",
            "--format", "json",
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["decision"] == "allow"
        assert "call_id" in data or "factors" in data

    def test_explain_output(self) -> None:
        result = _run(
            "explain",
            "--tool", "deploy_service",
            "--action", "write",
            "--env", "production",
            "--data", "restricted",
            "--agent", "release-bot",
        )
        assert "ESCALATE" in result.stdout
        assert "risk factor" in result.stdout.lower() or "factor" in result.stdout.lower()

    def test_init_all_postures(self) -> None:
        for posture in ("balanced", "strict", "permissive"):
            with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
                result = _run("init", "--posture", posture, "-o", f.name)
                assert result.returncode == 0
                content = Path(f.name).read_text()
                assert posture in content
                Path(f.name).unlink()

    def test_check_valid(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False, mode="w") as f:
            subprocess.run(
                ["uv", "run", "tooltrust", "init", "-o", f.name],
                capture_output=True, timeout=10,
            )
        result = _run("check", f.name)
        assert result.returncode == 0
        Path(f.name).unlink()

    def test_check_invalid(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False, mode="w") as f:
            f.write("invalid: [\n")
        result = _run("check", f.name)
        assert result.returncode != 0
        Path(f.name).unlink()

    def test_diff_output(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
            subprocess.run(
                ["uv", "run", "tooltrust", "init", "-o", f.name],
                capture_output=True, timeout=10,
            )
        result = _run("diff", f.name)
        assert result.returncode == 0
        Path(f.name).unlink()

    def test_field_test(self) -> None:
        result = _run(
            "field-test",
            "--agents", "lg-01",
            "--matrix", "decision",
            "--report", "none",
        )
        assert result.returncode == 0
        assert "Pass rate" in result.stdout

    def test_missing_required_args_fails(self) -> None:
        result = _run("evaluate")
        assert result.returncode != 0
        assert "required" in result.stderr.lower() or "error" in result.stderr.lower()
