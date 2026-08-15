"""``tooltrust audit`` — query and export the audit trail.

Subcommands:
* ``show`` — print every entry for a session (JSON or CSV).
* ``query`` — filter by decision/agent/since and print matching entries.
* ``export`` — write entries (per session, or all) as CSV or JSON to stdout.
* ``session`` — replay a session's cumulative state from its audit entries.
* ``verify`` — check the audit log's hash-chain integrity.

The sink defaults to the JSONL file ``~/.tooltrust/audit.jsonl``; pass
``--sink sqlite`` or ``--sink postgres`` to read another backend, and
``--path``/``--url`` to point at a non-default store.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from typing import Any

from agent_tooltrust.audit.logger import AuditLogger
from agent_tooltrust.audit.replay import replay_session
from agent_tooltrust.audit.sinks.jsonl import JsonlSink
from agent_tooltrust.audit.sinks.postgres import PostgresSink
from agent_tooltrust.audit.sinks.sqlite import SqliteSink
from agent_tooltrust.audit.tamper_proof import (
    build_hash_chain,
    sign_root,
    verify_entries,
    verify_signature,
)
from agent_tooltrust.cli.errors import CliError

_FIELDS = (
    "session_id",
    "timestamp",
    "tool",
    "action",
    "environment",
    "data_class",
    "agent_id",
    "decision",
    "criticality",
    "reason_code",
    "explanation",
    "policy_version",
    "dry_run",
    "escalation_id",
)


def add_parser(subparsers: Any) -> None:
    """Register the ``tooltrust audit`` subcommand parser.

    Args:
        subparsers: The ``add_subparsers()`` action from the parent parser.
    """
    parser = subparsers.add_parser(
        "audit",
        help="query and export the audit trail",
        description="Inspect audit entries written by the engine.",
    )
    sub = parser.add_subparsers(dest="audit_command", required=True, metavar="SUBCOMMAND")

    show = sub.add_parser("show", help="show entries for a session")
    _add_sink_args(show)
    show.add_argument("--session", required=True, help="session id to show")
    show.add_argument("--format", choices=["json", "csv"], default="json")
    show.set_defaults(func=_run_show)

    query = sub.add_parser("query", help="filter audit entries")
    _add_sink_args(query)
    query.add_argument("--session", help="session id filter")
    query.add_argument("--decision", help="decision filter (allow/audit/escalate/deny)")
    query.add_argument("--agent", help="agent id filter")
    query.add_argument("--since", help="ISO timestamp filter (>=)")
    query.add_argument("--format", choices=["json", "csv"], default="json")
    query.set_defaults(func=_run_query)

    export = sub.add_parser("export", help="export entries (CSV or JSON)")
    _add_sink_args(export)
    export.add_argument("--session", help="session id filter (default: all)")
    export.add_argument("--format", choices=["json", "csv"], default="csv")
    export.set_defaults(func=_run_export)

    session = sub.add_parser("session", help="replay a session from the audit trail")
    _add_sink_args(session)
    session.add_argument(
        "--replay",
        required=True,
        metavar="SESSION_ID",
        help="session id to replay (reconstructs cumulative risk at each call)",
    )
    session.set_defaults(func=_run_session)

    verify = sub.add_parser("verify", help="verify audit log integrity")
    _add_sink_args(verify)
    verify.add_argument("--sign", action="store_true", help="Sign root entry with ed25519")
    verify.set_defaults(func=_run_verify)


def _add_sink_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--sink", choices=["jsonl", "sqlite", "postgres"], default="jsonl")
    parser.add_argument("--path", help="file path for jsonl/sqlite sinks")
    parser.add_argument("--url", help="connection URL for postgres sink")


def _build_sink(args: argparse.Namespace) -> Any:
    if args.sink == "jsonl":
        return JsonlSink(args.path or "~/.tooltrust/audit.jsonl")
    if args.sink == "sqlite":
        return SqliteSink(args.path)
    return PostgresSink(args.url or _require_url())


def _require_url() -> str:
    raise CliError("--url is required when --sink postgres")


def _run_show(args: argparse.Namespace) -> int:
    logger = AuditLogger(_build_sink(args))
    entries = logger.query(args.session)
    _emit(entries, args.format)
    return 0


def _run_query(args: argparse.Namespace) -> int:
    logger = AuditLogger(_build_sink(args))
    entries = logger.query(args.session)
    if args.decision:
        entries = [e for e in entries if e.decision == args.decision]
    if args.agent:
        entries = [e for e in entries if e.agent_id == args.agent]
    if args.since:
        entries = [e for e in entries if e.timestamp >= args.since]
    _emit(entries, args.format)
    return 0


def _run_export(args: argparse.Namespace) -> int:
    logger = AuditLogger(_build_sink(args))
    entries = logger.query(args.session)
    _emit(entries, args.format)
    return 0


def _run_session(args: argparse.Namespace) -> int:
    """Replay one session's cumulative state from the audit trail.

    The whole log's hash chain is verified first, because a session's entries
    are only trustworthy if every entry linking into them survived unmodified.
    A tampered, missing, or un-chained entry aborts with exit code 1 — replay
    of a corrupted log would silently report invented risk.

    Args:
        args: Parsed arguments (requires ``--replay <session_id>``).

    Returns:
        Exit code 0 on success; exit code 1 if the log fails integrity
        checking; a session with no recorded entries replays as an empty
        timeline (call_count 0), not an error.
    """
    logger = AuditLogger(_build_sink(args))
    integrity = verify_entries(logger.query())
    if not integrity["valid"]:
        print(f"✗ Replay aborted: tampered or missing entry at index {integrity['tampered_index']}")
        return 1
    entries = logger.query(args.replay)
    replay = replay_session(entries, session_id=args.replay)
    print(json.dumps(replay.to_dict(), indent=2))
    return 0


def _run_verify(args: argparse.Namespace) -> int:
    """Verify audit log integrity via the persisted hash chain.

    Args:
        args: Parsed arguments.

    Returns:
        Exit code 0 if valid, 1 if tampered or unverifiable.
    """
    logger = AuditLogger(_build_sink(args))
    entries = logger.query()

    if not entries:
        print("No audit entries to verify.")
        return 0

    result = verify_entries(entries)
    if result["valid"]:
        print(f"✓ Audit log is intact ({len(entries)} entries)")
    else:
        print(f"✗ Tampering detected at index {result['tampered_index']}")
        return 1

    if args.sign:
        chained = build_hash_chain(entries)
        signed = sign_root(chained)
        valid = verify_signature(signed)
        if valid:
            print(f"  Signature valid (root {signed['chain_hash'][:12]}...)")
        else:
            print("  Signature verification failed")
            return 1

    return 0


def _emit(entries: list[Any], fmt: str) -> None:
    if fmt == "json":
        print(json.dumps([e.to_dict() for e in entries], indent=2))
        return
    writer = csv.DictWriter(sys.stdout, fieldnames=list(_FIELDS), extrasaction="ignore")
    writer.writeheader()
    for entry in entries:
        writer.writerow({field: getattr(entry, field) for field in _FIELDS})
