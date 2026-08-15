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

_PACKS_DIR = Path(__file__).resolve().parents[3] / "packs"


def list_packs() -> list[dict[str, Any]]:
    """Return metadata for every pack in the packs/ directory."""
    import yaml

    if not _PACKS_DIR.is_dir():
        return []
    packs: list[dict[str, Any]] = []
    for child in sorted(_PACKS_DIR.iterdir()):
        if child.is_dir():
            meta_path = child / "metadata.yaml"
            if meta_path.exists():
                with open(meta_path) as f:
                    meta = yaml.safe_load(f)
                if meta is not None:
                    packs.append(meta)
    return packs


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

    list_parser = sub.add_parser(
        "list",
        help="list available policy packs in the catalog",
    )
    list_parser.set_defaults(pack_func=_run_list)

    info_parser = sub.add_parser(
        "info",
        help="show metadata for a single pack",
    )
    info_parser.add_argument("name", help="pack name (directory under packs/)")
    info_parser.set_defaults(pack_func=_run_info)

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


def _run_list(args: argparse.Namespace) -> int:
    packs = list_packs()
    if not packs:
        print("No packs found in the catalog.")
        return 0
    print(f"{'Name':<20} {'Domains':<30} {'Tools':<8} {'Tests':<8} {'Updated':<14} {'Maintainer'}")
    print("-" * 90)
    for p in packs:
        domains = ", ".join(p.get("domains", []))
        print(
            f"{p['name']:<20} {domains:<30} "
            f"{p.get('tool_count', '?'):<8} {p.get('tests_passing', '?'):<8} "
            f"{p.get('last_updated', 'unknown'):<14} {p.get('maintainer', 'unknown')}"
        )
    return 0


def _run_info(args: argparse.Namespace) -> int:
    import yaml

    path = _PACKS_DIR / args.name / "metadata.yaml"
    if not path.exists():
        raise CliError(f"Pack '{args.name}' not found in catalog.")
    with open(path) as f:
        meta = yaml.safe_load(f)
    for k, v in meta.items():
        print(f"{k}: {v}")
    return 0
