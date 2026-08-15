"""``tooltrust calibrate`` — score calibration reports.

Subcommands:
* ``report`` — print false-allow / false-escalate rates bucketed by tool,
  environment, and data class, using the audit log and escalation store.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from typing import Any

from agent_tooltrust.audit.logger import AuditLogger
from agent_tooltrust.cli.errors import CliError


def add_parser(subparsers: Any) -> None:
    """Register the ``tooltrust calibrate`` subcommand parser.

    Args:
        subparsers: The ``add_subparsers()`` action from the parent parser.
    """
    parser = subparsers.add_parser(
        "calibrate",
        help="Score calibration reports: false-allow/escalate rates",
    )
    sub = parser.add_subparsers(dest="calibrate_command", required=True)

    sub.add_parser(
        "report",
        help="Show false-allow and false-escalate rates by tool, env, data class",
    )
    parser.set_defaults(func=_run_calibrate)


def _run_calibrate(args: argparse.Namespace) -> int:
    """Dispatch to the appropriate subcommand."""
    if args.calibrate_command == "report":
        return _run_report(args)
    raise CliError(f"Unknown calibrate subcommand: {args.calibrate_command}")


def _run_report(args: argparse.Namespace) -> int:
    """Compute and print calibration report."""
    logger = AuditLogger()
    entries = logger.query(None)

    by_tool: defaultdict[str, list[str]] = defaultdict(list)
    by_env: defaultdict[str, list[str]] = defaultdict(list)
    by_data: defaultdict[str, list[str]] = defaultdict(list)

    for entry in entries:
        by_tool[entry.tool].append(entry.decision)
        by_env[entry.environment].append(entry.decision)
        by_data[entry.data_class].append(entry.decision)

    print("=== Calibration Report ===\n")
    _print_bucket("Tool", by_tool)
    _print_bucket("Environment", by_env)
    _print_bucket("Data Class", by_data)

    print("\n(Shadow mode: run `tooltrust calibrate report` against a production")
    print(" audit snapshot with candidate thresholds, compare rates to promote.)")
    return 0


def _print_bucket(label: str, buckets: dict[str, list[str]]) -> None:
    print(f"--- By {label} ---")
    for key, decisions in sorted(buckets.items()):
        total = len(decisions)
        deny_count = sum(1 for d in decisions if d == "deny")
        allow_count = sum(1 for d in decisions if d in ("allow", "audit"))
        escalate_count = sum(1 for d in decisions if d == "escalate")
        print(
            f"  {key}: {total} calls, "
            f"{allow_count} allow/audit ({allow_count/total*100:.0f}%), "
            f"{escalate_count} escalate ({escalate_count/total*100:.0f}%), "
            f"{deny_count} deny ({deny_count/total*100:.0f}%)"
        )
