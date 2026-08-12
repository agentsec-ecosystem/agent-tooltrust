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

from agent_tooltrust.cli import audit, check, diff, init
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
        version="tooltrust 0.1.0",
    )
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")
    init.add_parser(subparsers)
    check.add_parser(subparsers)
    diff.add_parser(subparsers)
    audit.add_parser(subparsers)
    serve_cli.add_parser(subparsers)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI. Returns a process exit code (0 = success).

    Subcommand modules raise :class:`cli.CliError` for user-facing failures;
    we print the message to stderr and return 1 so scripts see a non-zero code
    without a traceback.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except CliError as exc:
        print(f"tooltrust: error: {exc}", file=sys.stderr)
        return 1


def _climain(argv: Sequence[str] | None = None) -> NoReturn:
    """Console-script wrapper: always raises SystemExit with the exit code."""
    raise SystemExit(main(argv))


if __name__ == "__main__":
    _climain()
