"""``tooltrust init`` — write a posture preset as ``tooltrust.yaml``."""

from __future__ import annotations

import argparse

from agent_tooltrust.policy.postures import available_postures, init_policy


def add_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "init",
        help="write a posture preset as tooltrust.yaml",
        description="Generate a tooltrust.yaml from a shipped posture preset.",
    )
    parser.add_argument(
        "--posture",
        choices=available_postures(),
        default="balanced",
        help="posture preset to write (default: balanced)",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="output path (default: ./tooltrust.yaml)",
    )
    parser.set_defaults(func=_run)


def _run(args: argparse.Namespace) -> int:
    path = init_policy(args.posture, args.output)
    print(f"wrote {path}")
    return 0
