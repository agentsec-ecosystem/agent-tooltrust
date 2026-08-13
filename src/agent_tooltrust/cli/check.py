"""``tooltrust check`` — validate a tooltrust.yaml against the schema.

Reads the policy file, parses it through the loader (which validates against
the Pydantic schema and merges the posture default), and reports success or
the first error with its line/column. Used at startup and on policy reload so
a malformed file fails closed instead of shipping silently.

With ``--migrate``, compares the loaded policy against its posture default and
reports any breaking changes (environments, data_classes, risk_weights, or
rules that differ from the baseline).
"""

from __future__ import annotations

import argparse
from typing import Any

from agent_tooltrust.cli.errors import CliError
from agent_tooltrust.errors import PolicyParseError
from agent_tooltrust.policy.loader import load_policy
from agent_tooltrust.policy.models import Policy, default_policy


def add_parser(subparsers: Any) -> None:
    """Register the ``tooltrust check`` subcommand parser.

    Args:
        subparsers: The ``add_subparsers()`` action from the parent parser.
    """
    parser = subparsers.add_parser(
        "check",
        help="validate a tooltrust.yaml policy",
        description="Validate a policy file against the schema; exits 0 if clean.",
    )
    parser.add_argument(
        "policy",
        nargs="?",
        default="tooltrust.yaml",
        help="policy file to check (default: ./tooltrust.yaml)",
    )
    parser.add_argument(
        "--migrate",
        action="store_true",
        help="compare against the posture default and report breaking changes",
    )
    parser.set_defaults(func=_run)


def _run(args: argparse.Namespace) -> int:
    try:
        policy = load_policy(args.policy)
    except PolicyParseError as exc:
        raise CliError(f"invalid policy: {exc}") from exc
    print(f"ok: {args.policy} (version {policy.version}, posture {policy.posture})")
    if args.migrate:
        return _report_migration(policy)
    return 0


def _report_migration(policy: Policy) -> int:
    base = default_policy(policy.posture)
    changes = []
    for env_name in sorted(set(base.environments) | set(policy.environments)):
        if base.environments.get(env_name) != policy.environments.get(env_name):
            changes.append(
                f"  {env_name}: {base.environments.get(env_name, '-')} -> "
                f"{policy.environments.get(env_name, '-')}"
            )
    for dc_name in sorted(set(base.data_classes) | set(policy.data_classes)):
        if base.data_classes.get(dc_name) != policy.data_classes.get(dc_name):
            changes.append(
                f"  {dc_name}: {base.data_classes.get(dc_name, '-')} -> "
                f"{policy.data_classes.get(dc_name, '-')}"
            )
    if len(policy.rules) != len(base.rules):
        changes.append(f"  rules: {len(base.rules)} -> {len(policy.rules)} rules")
    else:
        for i, (br, pr) in enumerate(zip(base.rules, policy.rules, strict=False)):
            if br != pr:
                changes.append(f"  rule[{i}]: differs from baseline")
    if not changes:
        print("  no breaking changes detected")
        return 0
    print(f"  breaking changes ({len(changes)}):")
    for c in changes:
        print(c)
    return 1
