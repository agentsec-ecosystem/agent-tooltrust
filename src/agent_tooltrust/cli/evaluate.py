"""``tooltrust evaluate`` — evaluate a tool call and print the decision."""

from __future__ import annotations

import argparse
import json
from typing import Any

from agent_tooltrust.cli.errors import CliError
from agent_tooltrust.engine.engine import Engine
from agent_tooltrust.policy.loader import load_policy
from agent_tooltrust.policy.models import default_policy


def add_parser(subparsers: Any) -> None:
    """Register the ``tooltrust evaluate`` subcommand parser.

    Args:
        subparsers: The ``add_subparsers()`` action from the parent parser.
    """
    parser = subparsers.add_parser(
        "evaluate",
        help="evaluate a tool call against the policy",
        description="Run a tool call through the decision engine and print the result.",
    )
    parser.add_argument("--tool", required=True, help="Tool name (e.g., query_logs)")
    parser.add_argument("--action", required=True, help="Action verb (e.g., read, write)")
    parser.add_argument("--env", required=True, help="Environment (e.g., staging, production)")
    parser.add_argument("--data", required=True, help="Data class (e.g., internal, restricted)")
    parser.add_argument("--agent", required=True, help="Agent identity (e.g., debug-bot)")
    parser.add_argument("--session", default=None, help="Optional session identifier")
    parser.add_argument("--dry-run", action="store_true",
                        help="Shadow mode: log decision, return allow")
    parser.add_argument("--format", choices=["table", "json"],
                        default="table", help="Output format")
    parser.add_argument("--policy", default=None, help="Path to tooltrust.yaml")
    parser.set_defaults(func=_evaluate)


def _evaluate(args: argparse.Namespace) -> int:
    """Evaluate a tool call and print the decision.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code 0 on success, 1 on error.
    """

    try:
        if args.policy:
            policy = load_policy(args.policy)
        else:
            policy = default_policy("balanced")
        engine = Engine(policy, dry_run=args.dry_run)
        decision = engine.evaluate(
            tool_name=args.tool,
            action=args.action,
            environment=args.env,
            data_class=args.data,
            agent_id=args.agent,
        )
    except Exception as exc:
        raise CliError(str(exc)) from exc

    if args.format == "json":
        print(json.dumps(decision.to_dict(), indent=2))
    else:
        _print_table(decision)

    return 2 if decision.decision == "deny" else 0


def _print_table(decision: Any) -> None:
    """Print a Decision as a formatted ASCII table.

    Args:
        decision: The Decision object from the engine.
    """
    indicator = _decision_indicator(decision.decision)
    print()
    print(f"  Decision      {indicator} {decision.decision.upper()}")
    print(f"  Criticality   {decision.criticality}")
    print(f"  Reason code   {decision.reason_code}")
    print(f"  Explanation   {decision.explanation}")
    print(f"  Policy        v{decision.policy_version}")
    if decision.factors:
        print("  Factors")
        for f in decision.factors:
            print(f"    {f.dimension:20s} {f.value:20s} contribution={f.contribution:.2f}")
    print()


def _decision_indicator(decision: str) -> str:
    """Return a visual indicator for the decision type.

    Args:
        decision: The decision string (allow, audit, escalate, deny).

    Returns:
        A colored indicator symbol.
    """
    indicators: dict[str, str] = {
        "allow": "✓",
        "audit": "⚑",
        "escalate": "⤴",
        "deny": "✗",
    }
    return indicators.get(decision, "?")
