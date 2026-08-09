"""``tooltrust check`` — validate a tooltrust.yaml against the schema.

Reads the policy file, parses it through the loader (which validates against
the Pydantic schema and merges the posture default), and reports success or
the first error with its line/column. Used at startup and on policy reload so
a malformed file fails closed instead of shipping silently.
"""

from __future__ import annotations

import argparse

from agent_tooltrust.cli.errors import CliError
from agent_tooltrust.errors import PolicyParseError
from agent_tooltrust.policy.loader import load_policy


def add_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
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
    parser.set_defaults(func=_run)


def _run(args: argparse.Namespace) -> int:
    try:
        policy = load_policy(args.policy)
    except PolicyParseError as exc:
        raise CliError(f"invalid policy: {exc}") from exc
    print(f"ok: {args.policy} (version {policy.version}, posture {policy.posture})")
    return 0
