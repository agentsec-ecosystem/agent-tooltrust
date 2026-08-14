"""``tooltrust pack`` — validate and test policy packs (M1 #91).

A pack is a directory shipping a ``tools.yaml`` policy document plus an
optional ``tests.yaml`` of golden decision fixtures. ``validate`` parses both
files against the schemas and checks internal consistency (duplicate tool
names, undeclared fixture tools); ``test`` replays the fixtures through the
Engine deterministically and reports pass/fail per fixture.

Exit codes: 0 = ok, 1 = validation/test failure or user error.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from agent_tooltrust.cli.errors import CliError
from agent_tooltrust.policy.pack import PackError, run_pack_tests, validate_pack


def add_parser(subparsers: Any) -> None:
    """Register the ``tooltrust pack`` subcommand parser.

    Args:
        subparsers: The ``add_subparsers()`` action from the parent parser.
    """
    parser = subparsers.add_parser(
        "pack",
        help="validate and test policy packs",
        description="Validate a tooltrust policy pack (tools.yaml + tests.yaml) and run its tests.",
    )
    sub = parser.add_subparsers(dest="pack_command", required=True, metavar="COMMAND")

    validate_parser = sub.add_parser(
        "validate",
        help="validate a policy pack",
        description="Validate the pack's tools.yaml and tests.yaml; exits 0 if clean.",
    )
    validate_parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="pack directory or path to its tools.yaml (default: .)",
    )
    validate_parser.set_defaults(pack_func=_run_validate)

    test_parser = sub.add_parser(
        "test",
        help="run a policy pack's test fixtures",
        description="Replay the pack's golden fixtures; exits 0 if all pass.",
    )
    test_parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="pack directory or path to its tools.yaml (default: .)",
    )
    test_parser.set_defaults(pack_func=_run_test)

    parser.set_defaults(func=_run)


def _run(args: argparse.Namespace) -> int:
    """Dispatch to the pack sub-subcommand given by ``args.pack_command``."""
    return int(args.pack_func(args))


def _run_validate(args: argparse.Namespace) -> int:
    try:
        errors, policy = validate_pack(args.path)
    except PackError as exc:
        raise CliError(str(exc)) from exc
    if errors:
        raise CliError("; ".join(errors))
    print(
        f"ok: {Path(args.path)} "
        f"(version {policy.version}, posture {policy.posture})"
    )
    return 0


def _run_test(args: argparse.Namespace) -> int:
    try:
        results = run_pack_tests(args.path)
    except PackError as exc:
        raise CliError(str(exc)) from exc
    if not results:
        print(f"no tests.yaml in {Path(args.path)}: 0 fixtures")
        return 0
    failed = 0
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        if not result.passed:
            failed += 1
        print(
            f"{status} {result.name}: expected={result.expected} "
            f"got={result.decision}"
        )
    print(f"{len(results) - failed}/{len(results)} passed")
    return 0 if failed == 0 else 1
