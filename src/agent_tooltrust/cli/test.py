"""``tooltrust test`` — replay golden fixtures for CI policy regression."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

from agent_tooltrust.cli.errors import CliError
from agent_tooltrust.engine.engine import Engine
from agent_tooltrust.policy.loader import load_policy
from agent_tooltrust.policy.models import default_policy


def add_parser(subparsers: Any) -> None:
    """Register the ``tooltrust test`` subcommand parser.

    Args:
        subparsers: The ``add_subparsers()`` action from the parent parser.
    """
    parser = subparsers.add_parser(
        "test",
        help="run policy regression tests against golden fixtures",
        description="Replay golden fixtures and report pass/fail per scenario.",
    )
    parser.add_argument(
        "--fixtures", default="tests/fixtures/acceptance_matrix.yaml",
        help="Path to YAML fixtures file",
    )
    parser.add_argument("--policy", default=None, help="Path to tooltrust.yaml")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    parser.set_defaults(func=_test)


def _test(args: argparse.Namespace) -> int:
    """Replay golden fixtures and report results.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code 0 if all pass, 1 if any fail.
    """
    try:
        if args.policy:
            policy = load_policy(args.policy)
        else:
            policy = default_policy("balanced")
        engine = Engine(policy)

        data, cells = _load_fixtures(args.fixtures)
    except Exception as exc:
        raise CliError(str(exc)) from exc

    default_agent = (
        str(data.get("agent_id", "test-agent"))
        if isinstance(data, dict)
        else "test-agent"
    )
    passed = 0
    failed = 0
    failures: list[dict[str, Any]] = []

    for cell in cells:
        agent = str(cell.get("agent_id") or cell.get("agent") or default_agent)
        decision = engine.evaluate(
            tool_name=str(cell.get("tool", "")),
            action=str(cell.get("action", "")),
            environment=str(cell.get("environment", cell.get("env", ""))),
            data_class=str(cell.get("data_class", cell.get("data", ""))),
            agent_id=agent,
        )
        actual = decision.decision
        expected = cell.get("expected") or cell.get("decision")

        if expected and actual == expected:
            passed += 1
        elif expected:
            failed += 1
            failures.append({
                "tool": cell.get("tool"),
                "action": cell.get("action"),
                "expected": expected,
                "actual": actual,
                "reason": decision.reason_code,
            })
        else:
            passed += 1

    if args.json:
        print(json.dumps({"passed": passed, "failed": failed, "failures": failures}, indent=2))
    else:
        print(f"  Passed: {passed}")
        print(f"  Failed: {failed}")
        for f in failures:
            tool = f["tool"]
            action = f["action"]
            exp = f["expected"]
            act = f["actual"]
            reason = f["reason"]
            print(f"    x {tool} ({action}): expected {exp}, got {act} [{reason}]")

    return 0 if failed == 0 else 1


def _load_fixtures(path: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Load fixtures from a YAML file.

    Args:
        path: Path to the YAML fixtures file.

    Returns:
        A tuple of (raw_data, cell_list) where cell_list contains per-scenario dicts
        with tool/action/environment/data_class/decision fields.
    """
    fixture_path = Path(path)
    if not fixture_path.exists():
        raise CliError(f"Fixture file not found: {path}")

    data: dict[str, Any] = yaml.safe_load(fixture_path.read_text()) or {}
    if isinstance(data, dict):
        if "cells" in data:
            return data, data["cells"]
        if "scenarios" in data:
            return data, data["scenarios"]
        if "fixtures" in data:
            return data, data["fixtures"]
        return data, []
    if isinstance(data, list):
        return {}, data
    return {}, []
