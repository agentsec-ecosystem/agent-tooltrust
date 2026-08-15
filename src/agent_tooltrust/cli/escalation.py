"""``tooltrust escalation`` — human approval round-trip (M3, F-90, #85).

Subcommands:

* ``list`` — show pending escalations (and optionally all, via ``--all``).
* ``approve <id>`` — approve a pending escalation (records approver + time).
* ``deny <id>`` — deny a pending escalation (records approver + reason).

Approvals and denials persist to ``~/.tooltrust/escalations.json`` so a human
can review an escalation created by an earlier engine process. The default
file can be overridden with ``--file`` for scripting and CI.
"""

from __future__ import annotations

import argparse
from typing import Any

from agent_tooltrust.audit.models import AuditEntry
from agent_tooltrust.audit.sinks.jsonl import JsonlSink
from agent_tooltrust.cli.errors import CliError
from agent_tooltrust.engine.escalation import Escalation, EscalationManager, EscalationStatus

_DEFAULT_FILE = "~/.tooltrust/escalations.json"


def add_parser(subparsers: Any) -> None:
    """Register the ``tooltrust escalation`` subcommand parser.

    Args:
        subparsers: The ``add_subparsers()`` action from the parent parser.
    """
    parser = subparsers.add_parser(
        "escalation",
        help="review and approve/deny escalations",
        description="Human approval round-trip for escalated tool calls.",
    )
    sub = parser.add_subparsers(dest="escalation_command", required=True, metavar="COMMAND")
    _add_list_parser(sub)
    _add_approve_parser(sub)
    _add_deny_parser(sub)


def _file_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--file",
        default=_DEFAULT_FILE,
        help=f"Escalation store path (default: {_DEFAULT_FILE})",
    )


def _add_list_parser(sub: Any) -> None:
    parser = sub.add_parser("list", help="list escalations")
    parser.add_argument("--all", action="store_true", dest="show_all",
                        help="show resolved escalations too")
    _file_option(parser)
    parser.set_defaults(func=_list)


def _add_approve_parser(sub: Any) -> None:
    parser = sub.add_parser("approve", help="approve an escalation")
    parser.add_argument("id", help="Escalation id (e.g. esc_abcdef)")
    parser.add_argument("--approver", default=None,
                        help="Approver identity (default: $USER)")
    _file_option(parser)
    parser.set_defaults(func=_approve)


def _add_deny_parser(sub: Any) -> None:
    parser = sub.add_parser("deny", help="deny an escalation")
    parser.add_argument("id", help="Escalation id (e.g. esc_abcdef)")
    parser.add_argument("--reason", default="", help="Denial reason")
    parser.add_argument("--approver", default=None,
                        help="Approver identity (default: $USER)")
    _file_option(parser)
    parser.set_defaults(func=_deny)


def _approver(args: argparse.Namespace) -> str:
    """Resolve the approver identity (explicit flag or $USER)."""
    explicit: Any = getattr(args, "approver", None)
    if explicit:
        return str(explicit)
    import getpass

    user = getpass.getuser()
    if not user:
        raise CliError("cannot determine approver; pass --approver <who>")
    return user


def _list(args: argparse.Namespace) -> int:
    """Print escalations (pending by default, all with ``--all``).

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code 0 on success.
    """
    manager = EscalationManager.load(args.file)
    records = list(manager.records.values())
    if not args.show_all:
        records = [r for r in records if r.status == EscalationStatus.PENDING]
    if not records:
        print("no escalations")
        return 0
    for record in records:
        print(
            f"{record.escalation_id}  {record.status.value:8s}  "
            f"{record.tool}.{record.action}  agent={record.agent_id}  "
            f"env={record.environment}  data={record.data_class}"
        )
        if record.approver:
            print(f"    approver={record.approver}" + (
                f" reason={record.denied_reason}" if record.denied_reason else ""
            ))
    return 0


def _approve(args: argparse.Namespace) -> int:
    """Approve a pending escalation, recording approver + time.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code 0 on success, 1 on unknown/resolved/expired escalation.
    """
    manager = EscalationManager.load(args.file)
    try:
        record = manager.approve(args.id, approver=_approver(args))
    except ValueError as exc:
        raise CliError(str(exc)) from exc
    manager.save(args.file)
    _write_audit(record, decision="allow")
    print(f"approved {record.escalation_id} by {record.approver}")
    return 0


def _deny(args: argparse.Namespace) -> int:
    """Deny a pending escalation, recording approver + reason.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code 0 on success, 1 on unknown/resolved/expired escalation.
    """
    manager = EscalationManager.load(args.file)
    try:
        record = manager.deny(
            args.id, approver=_approver(args), reason=args.reason
        )
    except ValueError as exc:
        raise CliError(str(exc)) from exc
    manager.save(args.file)
    _write_audit(record, decision="deny")
    print(f"denied {record.escalation_id} by {record.approver}")
    if record.denied_reason:
        print(f"reason: {record.denied_reason}")
    return 0


def _write_audit(record: Escalation, decision: str) -> None:
    """Append an audit entry recording an approve/deny decision.

    The audit trail gets a self-contained record of the human's action:
    escalation id, tool/action/environment/data, the approver, and the
    outcome (approved/denied). Failures are non-fatal — the escalation
    store already persisted the decision.

    Args:
        record: The resolved Escalation.
        decision: ``"allow"`` for an approval, ``"deny"`` for a denial.
    """
    entry = AuditEntry(
        session_id=None,
        timestamp=record.created_at,
        tool=record.tool,
        tool_category=None,
        action=record.action,
        action_class=None,
        environment=record.environment,
        data_class=record.data_class,
        agent_id=record.agent_id,
        agent_class=None,
        decision=decision,
        criticality="high",
        reason_code="allow_escalation_approved"
        if decision == "allow"
        else "deny_escalation_denied",
        explanation=record.denied_reason or f"escalation {record.escalation_id}",
        escalation_id=record.escalation_id,
        approver=record.approver,
    )
    JsonlSink("~/.tooltrust/audit.jsonl").write(entry)
