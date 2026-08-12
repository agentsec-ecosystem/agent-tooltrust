"""``tooltrust field-test`` — placeholder for the M7 field test harness."""

from __future__ import annotations

import argparse
from typing import Any


def add_parser(subparsers: Any) -> None:
    """Register the ``tooltrust field-test`` subcommand parser.

    Args:
        subparsers: The ``add_subparsers()`` action from the parent parser.
    """
    parser = subparsers.add_parser(
        "field-test",
        help="run the field test harness (M7 placeholder)",
        description="Run ToolTrust against real agent platforms. Full harness ships in M7.",
    )
    parser.set_defaults(func=_field_test)


def _field_test(args: argparse.Namespace) -> int:
    """Placeholder for the field test harness (M7).

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code 0.
    """
    print("Field test harness — full implementation in M7.")
    print("Planned: 10-agent sweep, 300 assertions, 40-cell decision matrix.")
    return 0
