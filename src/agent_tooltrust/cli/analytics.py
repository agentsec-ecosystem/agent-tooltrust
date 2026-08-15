"""``tooltrust analytics`` — session-to-session policy analytics CLI.

Subcommands:
* ``sessions`` — analyze the audit log for recurring denials, deny→allow
  transitions, dead rules, and over-hit rules.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from agent_tooltrust.analytics.session_analyzer import AnalyticsFindings, analyze
from agent_tooltrust.audit.logger import AuditLogger
from agent_tooltrust.cli.errors import CliError


def add_parser(subparsers: Any) -> None:
    """Register the ``tooltrust analytics`` subcommand parser.

    Args:
        subparsers: The ``add_subparsers()`` action from the parent parser.
    """
    parser = subparsers.add_parser(
        "analytics",
        help="Analyze the audit log for cross-session policy insights",
    )
    sub = parser.add_subparsers(dest="analytics_command", required=True)

    sessions_parser = sub.add_parser(
        "sessions",
        help="Detect recurring benign denials, deny→allow transitions, dead/over-hit rules",
    )
    sessions_parser.add_argument(
        "--min-denials",
        type=int,
        default=3,
        help="Minimum denials to flag a recurring pattern (default: 3)",
    )
    sessions_parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON findings instead of formatted text",
    )

    parser.set_defaults(func=_run_analytics)


def _run_analytics(args: argparse.Namespace) -> int:
    """Dispatch to the appropriate subcommand.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code (0 on success).
    """
    if args.analytics_command == "sessions":
        return _run_sessions(args)
    raise CliError(f"Unknown analytics subcommand: {args.analytics_command}")


def _run_sessions(args: argparse.Namespace) -> int:
    """Run the session-to-session analyzer and print findings.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code (0 on success).
    """
    logger = AuditLogger()
    entries = logger.query(None)
    findings = analyze(entries, min_denials=args.min_denials)

    if args.json:
        _print_json(findings)
    else:
        _print_text(findings)

    return 0


def _print_text(findings: AnalyticsFindings) -> None:
    """Print findings as human-readable text."""
    if findings.recurring_denials:
        print("=== Recurring Benign Denials ===")
        for d in findings.recurring_denials:
            tool, action, env, dc, agent = d.context
            print(f"  {tool}/{action} in {env} on {dc} by {agent}")
            print(f"    {d.deny_count}x denied — sample: {d.sample_reason}")

    if findings.deny_to_allow_transitions:
        print("\n=== Deny→Allow Transitions ===")
        for t in findings.deny_to_allow_transitions:
            tool, action, env, dc, agent = t.context
            print(f"  {tool}/{action} in {env} on {dc} by {agent}")
            print(f"    denied at {t.first_deny_at} → allowed at {t.first_allow_at}")

    if findings.dead_rules:
        print("\n=== Dead Rules (never matched) ===")
        for r in findings.dead_rules:
            print(f"  #{r.rule_index} {r.decision}: tool={r.tool} action={r.action} env={r.environment} data={r.data_class}")
            print(f"    reason: {r.reason}")

    if findings.over_hit_rules:
        print("\n=== Over-Hit Rules ===")
        for r in findings.over_hit_rules:
            print(f"  {r.reason_code}: {r.match_count}x (p{r.percentile})")

    if not any([findings.recurring_denials, findings.deny_to_allow_transitions,
                findings.dead_rules, findings.over_hit_rules]):
        print("No findings from the current audit log.")


def _print_json(findings: AnalyticsFindings) -> None:
    """Print findings as JSON to stdout."""
    data = {
        "recurring_denials": [
            {
                "context": list(r.context),
                "deny_count": r.deny_count,
                "sample_reason": r.sample_reason,
            }
            for r in findings.recurring_denials
        ],
        "deny_to_allow_transitions": [
            {
                "context": list(t.context),
                "first_deny_at": t.first_deny_at,
                "first_allow_at": t.first_allow_at,
            }
            for t in findings.deny_to_allow_transitions
        ],
        "dead_rules": [
            {
                "rule_index": r.rule_index,
                "decision": r.decision,
                "tool": r.tool,
                "action": r.action,
                "environment": r.environment,
                "data_class": r.data_class,
                "reason": r.reason,
            }
            for r in findings.dead_rules
        ],
        "over_hit_rules": [
            {
                "reason_code": r.reason_code,
                "match_count": r.match_count,
                "percentile": r.percentile,
            }
            for r in findings.over_hit_rules
        ],
    }
    json.dump(data, sys.stdout, indent=2)
    sys.stdout.write("\n")