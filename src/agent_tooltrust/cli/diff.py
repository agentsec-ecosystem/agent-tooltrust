"""``tooltrust diff`` — compare a policy against the default posture preset.

Lists kept defaults, overridden values, and gaps (sections not present in the
org overlay). Produces machine-parseable output for CI pipelines.
"""

from __future__ import annotations

import argparse
from typing import Any

from agent_tooltrust.cli.errors import CliError
from agent_tooltrust.errors import PolicyParseError
from agent_tooltrust.policy.loader import load_policy
from agent_tooltrust.policy.models import default_policy
from agent_tooltrust.policy.postures import available_postures


def add_parser(subparsers: Any) -> None:
    """Register the ``tooltrust diff`` subcommand parser.

    Args:
        subparsers: The ``add_subparsers()`` action from the parent parser.
    """
    parser = subparsers.add_parser(
        "diff",
        help="compare policy against the default posture preset",
        description="Compare a policy file against its posture default; show diffs.",
    )
    parser.add_argument(
        "policy",
        nargs="?",
        default="tooltrust.yaml",
        help="policy file to check (default: ./tooltrust.yaml)",
    )
    parser.add_argument(
        "--posture",
        choices=available_postures(),
        default=None,
        help="override posture inference (default: from file's posture field)",
    )
    parser.set_defaults(func=_run)


def _run(args: argparse.Namespace) -> int:
    try:
        org = load_policy(args.policy)
    except PolicyParseError as exc:
        raise CliError(f"cannot load policy: {exc}") from exc
    posture = args.posture if args.posture else org.posture
    base = default_policy(posture)
    print(f"--- base (posture {posture})")
    print(f"+++ policy ({args.policy})")
    for env_name in sorted(set(base.environments) | set(org.environments)):
        if base.environments.get(env_name) != org.environments.get(env_name):
            print(
                f"  environment {env_name}: "
                f"{base.environments.get(env_name, '-')} -> "
                f"{org.environments.get(env_name, '-')}"
            )
    for dc_name in sorted(set(base.data_classes) | set(org.data_classes)):
        if base.data_classes.get(dc_name) != org.data_classes.get(dc_name):
            print(
                f"  data_class: {dc_name}: "
                f"{base.data_classes.get(dc_name, '-')} -> "
                f"{org.data_classes.get(dc_name, '-')}"
            )
    for dim in sorted(set(base.risk_weights) | set(org.risk_weights)):
        if base.risk_weights.get(dim) != org.risk_weights.get(dim):
            print(
                f"  risk_weight {dim}: "
                f"{base.risk_weights.get(dim, '-')} -> "
                f"{org.risk_weights.get(dim, '-')}"
            )
    if org.rules != base.rules:
        print(f"  rules: {len(base.rules)} -> {len(org.rules)} rules")
    return 0 if org == base else 1
