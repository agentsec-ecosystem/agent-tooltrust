"""``tooltrust policy`` — manage policy lifecycle.

Subcommands:
* ``rollback`` — roll back to a previous policy version.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

from agent_tooltrust.cli.errors import CliError
from agent_tooltrust.policy.loader import load_policy


def add_parser(subparsers: Any) -> None:
    """Register the ``tooltrust policy`` subcommand parser.

    Args:
        subparsers: The ``add_subparsers()`` action from the parent parser.
    """
    parser = subparsers.add_parser(
        "policy",
        help="Manage policy lifecycle (rollback, inspect)",
    )
    sub = parser.add_subparsers(dest="policy_command", required=True)

    rollback_parser = sub.add_parser(
        "rollback",
        help="Roll back to a previous policy version",
    )
    rollback_parser.add_argument(
        "--version",
        required=True,
        help="Policy version to roll back to",
    )
    rollback_parser.add_argument(
        "--policy-path",
        default=None,
        help="Path to the policy directory (default: TOOLTRUST_POLICY_PATH env)",
    )
    parser.set_defaults(func=_run_policy)


def _run_policy(args: argparse.Namespace) -> int:
    if args.policy_command == "rollback":
        return _run_rollback(args)
    raise CliError(f"Unknown policy subcommand: {args.policy_command}")


def _run_rollback(args: argparse.Namespace) -> int:
    policy_path = args.policy_path or os.environ.get("TOOLTRUST_POLICY_PATH")
    if not policy_path:
        raise CliError(
            "Policy path not set. Pass --policy-path or set TOOLTRUST_POLICY_PATH."
        )

    path = Path(policy_path)
    version_dir = path / args.version
    tools_yaml = version_dir / "tools.yaml"
    if not tools_yaml.exists():
        raise CliError(f"Version '{args.version}' not found in {path}.")

    policy = load_policy(str(tools_yaml))
    print(f"Rolled back to version {args.version} (posture={policy.posture})")
    return 0
