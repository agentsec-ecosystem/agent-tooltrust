"""``tooltrust explain`` — explain why a tool call received its decision."""

from __future__ import annotations

import argparse
from typing import Any

from agent_tooltrust.cli.errors import CliError
from agent_tooltrust.engine.engine import Engine
from agent_tooltrust.engine.llm_explain import llm_explainer, template_explainer
from agent_tooltrust.policy.loader import load_policy
from agent_tooltrust.policy.models import default_policy


def add_parser(subparsers: Any) -> None:
    """Register the ``tooltrust explain`` subcommand parser.

    Args:
        subparsers: The ``add_subparsers()`` action from the parent parser.
    """
    parser = subparsers.add_parser(
        "explain",
        help="explain why a tool call received its decision",
        description="Run a tool call and print the factor breakdown with explanation.",
    )
    parser.add_argument("--tool", required=True, help="Tool name (e.g., deploy_service)")
    parser.add_argument("--action", required=True, help="Action verb (e.g., read, write)")
    parser.add_argument("--env", required=True, help="Environment (e.g., staging, production)")
    parser.add_argument("--data", required=True, help="Data class (e.g., internal, restricted)")
    parser.add_argument("--agent", required=True, help="Agent identity (e.g., release-bot)")
    parser.add_argument("--llm", action="store_true", help="Use LLM prose (falls back to template)")
    parser.add_argument("--policy", default=None, help="Path to tooltrust.yaml")
    parser.set_defaults(func=_explain)


def _explain(args: argparse.Namespace) -> int:
    """Evaluate and explain a tool call's decision.

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

        explainer = llm_explainer() if args.llm else template_explainer

        engine = Engine(policy, explainer=explainer)
        decision = engine.evaluate(
            tool_name=args.tool,
            action=args.action,
            environment=args.env,
            data_class=args.data,
            agent_id=args.agent,
        )
    except Exception as exc:
        raise CliError(str(exc)) from exc

    print()
    print(f"  Decision      {decision.decision.upper()}")
    print(f"  Reason        {decision.reason_code}")
    print(f"  Criticality   {decision.criticality}")
    print()
    print(f"  {decision.explanation}")
    print()
    if decision.factors:
        print("  Risk factor breakdown:")
        for f in decision.factors:
            bar = "█" * int(min(f.contribution * 20, 20))
            print(f"    {f.dimension:20s} {bar} ({f.contribution:.2f})")
    print()

    return 0
