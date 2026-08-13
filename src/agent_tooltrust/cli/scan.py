"""``tooltrust scan`` — scan tool definitions for adversarial patterns."""

from __future__ import annotations

import argparse
import json
from typing import Any

from agent_tooltrust.engine.scanner import scan_tool_definition


def add_parser(subparsers: Any) -> None:
    """Register the ``tooltrust scan`` subcommand parser.

    Args:
        subparsers: The ``add_subparsers()`` action from the parent parser.
    """
    parser = subparsers.add_parser(
        "scan",
        help="scan a tool definition for adversarial patterns",
        description="Detect hidden instructions, typosquatting, and adversarial patterns.",
    )
    parser.add_argument("--name", required=True, help="Tool name to scan")
    parser.add_argument("--desc", required=True, help="Tool description to scan")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.set_defaults(func=_scan)


def _scan(args: argparse.Namespace) -> int:
    """Scan a tool definition and report findings.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code 0 if clean, 1 if findings detected.
    """
    result = scan_tool_definition(args.name, args.desc)

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        if result.clean:
            print(f"✓ {result.tool_name} — clean")
        else:
            print(f"✗ {result.tool_name} — {len(result.findings)} issue(s) found")
            for finding in result.findings:
                print(f"  • {finding}")

    return 0 if result.clean else 1
