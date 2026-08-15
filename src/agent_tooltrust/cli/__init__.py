"""tooltrust CLI — package entry point.

Subcommands mirror the M2 policy-manager surface: ``init`` (write a posture
preset), ``check`` (validate a policy), ``diff`` (compare against the default
posture). Parsing uses argparse with the default ``--help``/``--version``
handling; each subcommand lives in its own module under ``cli/``.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from typing import NoReturn

from agent_tooltrust import __version__
from agent_tooltrust.cli import (
    analytics,
    audit,
    baseline,
    calibrate,
    check,
    diff,
    escalation,
    evaluate,
    explain,
    field_test,
    init,
    pack,
    report,
    scan,
    swebench,
    test,
)
from agent_tooltrust.cli.errors import CliError
from agent_tooltrust.server import cli as serve_cli


def _build_parser() -> argparse.ArgumentParser:
    """Construct the top-level argument parser with all subcommand parsers."""
    parser = argparse.ArgumentParser(
        prog="tooltrust",
        description="Pre-execution policy decision point for tool-using AI agents.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"tooltrust {__version__}",
    )
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")
    init.add_parser(subparsers)
    analytics.add_parser(subparsers)
    calibrate.add_parser(subparsers)
    check.add_parser(subparsers)
    baseline.add_parser(subparsers)
    diff.add_parser(subparsers)
    evaluate.add_parser(subparsers)
    explain.add_parser(subparsers)
    audit.add_parser(subparsers)
    field_test.add_parser(subparsers)
    scan.add_parser(subparsers)
    test.add_parser(subparsers)
    report.add_parser(subparsers)
    swebench.add_parser(subparsers)
    pack.add_parser(subparsers)
    serve_cli.add_parser(subparsers)
    escalation.add_parser(subparsers)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI. Returns a process exit code (0 = success).

    Subcommand modules raise :class:`cli.CliError` for user-facing failures;
    we print the message to stderr and return 1 so scripts see a non-zero code
    without a traceback.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)
    func = getattr(args, "func", None)
    if func is None:
        parser.print_usage(sys.stderr)
        return 2
    try:
        return int(func(args))
    except CliError as exc:
        print(f"tooltrust: error: {exc}", file=sys.stderr)
        return 1


def _climain(argv: Sequence[str] | None = None) -> NoReturn:
    """Console-script wrapper: always raises SystemExit with the exit code."""
    raise SystemExit(main(argv))


if __name__ == "__main__":
    _climain()
