"""``tooltrust swebench`` — run SWE-bench fixture tasks under ToolTrust policy."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from agent_tooltrust.cli.errors import CliError
from agent_tooltrust.engine.engine import Engine
from agent_tooltrust.integrations.swe_bench import (
    SWEBenchBenchmarkResult,
    SWEBenchRunner,
    swe_bench_policy,
)

_DEFAULT_FIXTURES = "tests/fixtures/swe_bench_tasks.yaml"


def add_parser(subparsers: Any) -> None:
    """Register the ``tooltrust swebench`` subcommand parser.

    Args:
        subparsers: The ``add_subparsers()`` action from the parent parser.
    """
    parser = subparsers.add_parser(
        "swebench",
        help="run SWE-bench fixture tasks under ToolTrust policy",
        description=(
            "Replay SWE-bench coding-agent tool calls through the ToolTrust wrapper "
            "and print per-task decision traces with flagged violations."
        ),
    )
    parser.add_argument(
        "--fixtures",
        default=_DEFAULT_FIXTURES,
        help="Path to SWE-bench task fixtures YAML",
    )
    parser.add_argument(
        "--policy",
        default=None,
        help="Path to a tooltrust.yaml policy; defaults to a swe_bench-tuned posture",
    )
    parser.add_argument(
        "--posture",
        choices=["strict", "balanced", "permissive"],
        default="balanced",
        help="Posture preset when no --policy is given (default: balanced)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output the full benchmark report as JSON",
    )
    parser.set_defaults(func=_swebench)


def _swebench(args: argparse.Namespace) -> int:
    """Run the SWE-bench fixtures and print a per-task decision trace.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code 0 on a completed run.
    """
    fixture_path = Path(args.fixtures)
    if not fixture_path.exists():
        raise CliError(f"SWE-bench fixtures file not found: {args.fixtures}")

    if args.policy:
        from agent_tooltrust.policy.loader import load_policy

        policy = load_policy(args.policy)
    else:
        policy = swe_bench_policy(args.posture)

    runner = SWEBenchRunner(Engine(policy))
    try:
        result: SWEBenchBenchmarkResult = runner.run_fixture(fixture_path)
    except Exception as exc:
        raise CliError(str(exc)) from exc

    if args.json:
        print(json.dumps(result.to_report(), indent=2))
    else:
        _print_trace(result)
    return 0


def _print_trace(result: SWEBenchBenchmarkResult) -> None:
    """Print a human-readable decision trace for a benchmark run.

    Args:
        result: The combined benchmark result to display.
    """
    for task in result.results:
        violations = len(task.violations)
        calls = task.total_calls
        print(f"\nTask {task.task_id}  ({calls} tool calls, {violations} violations)")
        for entry in task.decisions:
            flag = "VIOLATION" if entry["violation"] else "ok"
            tool = entry["tool"]
            action = entry["action"]
            decision = entry["decision"]
            reason = entry["reason_code"]
            print(f"  [{flag:9s}] {tool:<18s} {action:<7s} -> {decision:<8s} ({reason})")
            print(f"        {entry['command']}")
    completed = result.tasks_completed
    total = result.total_tasks
    flagged = result.violations_flagged
    print(f"\n{completed}/{total} tasks completed, {flagged} violations flagged")
