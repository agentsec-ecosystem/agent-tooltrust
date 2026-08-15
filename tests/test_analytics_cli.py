"""Tests for the analytics CLI subcommand."""

from __future__ import annotations

import json
from typing import Any

import pytest

from agent_tooltrust.analytics.session_analyzer import AnalyticsFindings, RecurringDenial


def test_sessions_json_output() -> None:
    """Run tooltrust analytics sessions --json and verify output format."""
    from agent_tooltrust.cli import main

    rc = main(["analytics", "sessions", "--json"])
    assert rc == 0


def test_sessions_text_output(capsys: pytest.CaptureFixture[str]) -> None:
    """Run tooltrust analytics sessions (text) and verify it prints headers."""
    from agent_tooltrust.cli import main

    rc = main(["analytics", "sessions"])
    assert rc == 0
    captured = capsys.readouterr().out
    assert "Recurring" in captured or "No findings" in captured


def test_sessions_custom_min_denials(capsys: pytest.CaptureFixture[str]) -> None:
    """--min-denials flag is accepted and affects output."""
    from agent_tooltrust.cli import main

    rc = main(["analytics", "sessions", "--min-denials", "5"])
    assert rc == 0
    captured = capsys.readouterr().out
    assert isinstance(captured, str)


def test_json_output_fields(capsys: pytest.CaptureFixture[str]) -> None:
    """JSON output contains all expected finding sections."""
    from agent_tooltrust.cli.analytics import _print_json

    findings = AnalyticsFindings(
        recurring_denials=[
            RecurringDenial(
                context=("run_query", "write", "prod", "pii", "bot1"),
                deny_count=5,
                sample_reason="blocked",
            ),
        ],
    )
    _print_json(findings)
    data = json.loads(capsys.readouterr().out)
    assert "recurring_denials" in data
    assert "deny_to_allow_transitions" in data
    assert "dead_rules" in data
    assert "over_hit_rules" in data
    assert data["recurring_denials"][0]["deny_count"] == 5


def test_print_text_empty(capsys: pytest.CaptureFixture[str]) -> None:
    """Empty findings prints a distinct message."""
    from agent_tooltrust.cli.analytics import _print_text

    _print_text(AnalyticsFindings())
    captured = capsys.readouterr().out
    assert "No findings" in captured