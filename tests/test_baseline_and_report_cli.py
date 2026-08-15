"""Test baseline CLI and report CLI execute successfully."""

from __future__ import annotations

from agent_tooltrust.cli import main


class TestBaselineCLI:
    def test_essential_check_runs(self) -> None:
        rc = main(["baseline", "check", "essential"])
        assert rc == 0

    def test_hardened_check_runs(self) -> None:
        rc = main(["baseline", "check", "hardened"])
        assert rc == 0


class TestReportCLI:
    def test_report_runs(self) -> None:
        rc = main(["report"])
        assert rc == 0
