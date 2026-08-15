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

    def test_pack_validate_ok(self) -> None:
        import shutil
        import tempfile as _temp

        d = Path(_temp.mkdtemp())
        (d / "tools.yaml").write_text('version: "1.0.0"\nposture: balanced\n')
        try:
            result = _run("pack", "validate", str(d))
            assert result.returncode == 0
            assert "ok" in result.stdout
        finally:
            shutil.rmtree(d)

    def test_pack_validate_rejects_malformed(self) -> None:
        import shutil
        import tempfile as _temp

        d = Path(_temp.mkdtemp())
        (d / "tools.yaml").write_text('version: "1.0.0"\nbogus: 1\n')
        try:
            result = _run("pack", "validate", str(d))
            assert result.returncode != 0
        finally:
            shutil.rmtree(d)

    def test_pack_test_passes(self) -> None:
        import shutil
        import tempfile as _temp

        d = Path(_temp.mkdtemp())
        (d / "tools.yaml").write_text('version: "1.0.0"\nposture: balanced\n')
        (d / "tests.yaml").write_text(
            'version: "1.0.0"\nfixtures:\n'
            "  - name: denied\n    tool: assign_role\n    action: grant\n"
            "    environment: production\n    data_class: restricted\n"
            "    agent_id: release-bot\n    expect: deny\n"
        )
        try:
            result = _run("pack", "test", str(d))
            assert result.returncode == 0
            assert "1/1 passed" in result.stdout
        finally:
            shutil.rmtree(d)

    def test_pack_test_reports_failure(self) -> None:
        import shutil
        import tempfile as _temp

        d = Path(_temp.mkdtemp())
        (d / "tools.yaml").write_text('version: "1.0.0"\nposture: balanced\n')
        (d / "tests.yaml").write_text(
            'version: "1.0.0"\nfixtures:\n'
            "  - name: wrongly-denied\n    tool: query_logs\n    action: read\n"
            "    environment: development\n    data_class: public\n"
            "    agent_id: release-bot\n    expect: deny\n"
        )
        try:
            result = _run("pack", "test", str(d))
            assert result.returncode == 1
            assert "FAIL" in result.stdout
        finally:
            shutil.rmtree(d)

    def test_evaluate_allow_with_obligation(self) -> None:
        import shutil
        import tempfile as _temp

        d = Path(_temp.mkdtemp())
        policy = d / "policy.yaml"
        policy.write_text(
            'version: "1.0.0"\nrules:\n'
            "  - decision: allow\n    action: delete\n"
            "    environment: production\n    obligations: [first_use_signoff]\n"
        )
        try:
            result = _run(
                "evaluate",
                "--tool", "drop_database",
                "--action", "delete",
                "--env", "production",
                "--data", "restricted",
                "--agent", "release-bot",
                "--policy", str(policy),
            )
            assert result.returncode == 0
            assert "ALLOW_WITH_OBLIGATION" in result.stdout
            assert "Obligations" in result.stdout
        finally:
            shutil.rmtree(d)
