"""``tooltrust field-test`` — run the M7 field test harness.

Loads the scenario matrix and agent roster, runs every (agent, scenario) pair
through the engine, asserts the expected decisions, and optionally writes a
markdown report. The field test is a release gate: any failure exits non-zero.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from agent_tooltrust.cli.errors import CliError
from agent_tooltrust.field.runner import FieldTestRunner

_DEFAULT_SCENARIOS = "tests/field/scenarios.yaml"
_DEFAULT_AGENTS = "tests/field/agents.yaml"
_DEFAULT_REPORT = "docs/field-test/field-test-report-v1.md"


def add_parser(subparsers: Any) -> None:
    """Register the ``tooltrust field-test`` subcommand parser.

    Args:
        subparsers: The ``add_subparsers()`` action from the parent parser.
    """
    parser = subparsers.add_parser(
        "field-test",
        help="run the M7 field test harness (release gate)",
        description="Run ToolTrust against the real-agent roster and scenario matrix.",
    )
    parser.add_argument(
        "--agents",
        default="all",
        help="Comma-separated agent ids, or 'all' (default: all)",
    )
    parser.add_argument(
        "--framework",
        default=None,
        help="Run only agents of this framework (e.g. langgraph, pydanticai)",
    )
    parser.add_argument(
        "--scenarios",
        default=_DEFAULT_SCENARIOS,
        help=f"Path to the scenario matrix YAML (default: {_DEFAULT_SCENARIOS})",
    )
    parser.add_argument(
        "--roster",
        default=_DEFAULT_AGENTS,
        help=f"Path to the agent roster YAML (default: {_DEFAULT_AGENTS})",
    )
    parser.add_argument(
        "--matrix",
        choices=["decision", "adversarial", "both"],
        default="both",
        help="Which sub-matrix to run (default: both)",
    )
    parser.add_argument(
        "--policy", default=None, help="Path to tooltrust.yaml (uses field policy by default)"
    )
    parser.add_argument(
        "--report",
        default=None,
        help=f"Write a markdown report to this path (default: {_DEFAULT_REPORT})",
    )
    parser.add_argument("--json", action="store_true", help="Output summary as JSON")
    parser.add_argument("--verbose", action="store_true", help="Print per-framework pass rates")
    parser.set_defaults(func=_field_test)


def _field_test(args: argparse.Namespace) -> int:
    """Run the field test harness.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code 0 if all cases pass, 1 otherwise.
    """
    try:
        runner = FieldTestRunner.from_files(args.scenarios, args.roster)
    except Exception as exc:
        raise CliError(f"failed to load field test inputs: {exc}") from exc

    if args.framework:
        runner._agents = [a for a in runner._agents if a.framework == args.framework]
        if not runner._agents:
            raise CliError(f"no agents found for framework {args.framework!r}")

    agent_ids = None if args.agents in ("all", "") else [a.strip() for a in args.agents.split(",")]
    scenario_types = None if args.matrix == "both" else [args.matrix]

    report = runner.run(agents=agent_ids, scenario_types=scenario_types)

    if args.json:
        print(
            json.dumps(
                {
                    "total": report.total,
                    "passed": report.passed,
                    "failed": report.failed,
                    "pass_rate": report.pass_rate(),
                    "framework_pass_rates": report.framework_pass_rates(),
                },
                indent=2,
            )
        )
    else:
        print(f"  Total cases:    {report.total}")
        print(f"  Passed:         {report.passed}")
        print(f"  Failed:         {report.failed}")
        print(f"  Pass rate:      {report.pass_rate():.1%}")

        if args.verbose:
            rates = report.framework_pass_rates()
            if rates:
                print("\n  Pass rate by framework:")
                for framework in sorted(rates):
                    print(f"    {framework:16} {rates[framework]:.1%}")

        for case in report.failures()[:10]:
            print(
                f"  x {case.scenario.id} / {case.agent.agent_id}: {case.notes}"
            )
        remaining = report.failed - 10
        if remaining > 0:
            print(f"  ... and {remaining} more failures")

    from agent_tooltrust.field.report import build_report

    report_path = args.report or _DEFAULT_REPORT
    if report_path and report_path != "none":
        path = Path(report_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(build_report(report), encoding="utf-8")
        if not args.json:
            print(f"\n  Report written to {report_path}")

    return 0 if report.failed == 0 else 1
