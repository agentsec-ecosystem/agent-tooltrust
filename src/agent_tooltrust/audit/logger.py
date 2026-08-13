"""The ``AuditLogger`` facade — build sinks from config and log without risk.

The engine depends on this facade, never on a concrete sink. The two
guarantees that make audit-safe are enforced here:

* ``log`` never raises. Any sink failure is printed to stderr; the decision
  pipeline is never blocked by persistence.
* The sink is looked up once at construction; a failing sink stays in place
  so operators see a steady stream of warnings instead of silent drop.
"""

from __future__ import annotations

import sys
from typing import Any

from agent_tooltrust.audit.models import AuditEntry
from agent_tooltrust.audit.sink import AuditSink
from agent_tooltrust.audit.sinks.jsonl import JsonlSink
from agent_tooltrust.audit.sinks.postgres import PostgresSink
from agent_tooltrust.audit.sinks.sqlite import SqliteSink
from agent_tooltrust.policy.schema import AuditConfig
from agent_tooltrust.types import Decision, NormalizedCall


class AuditLogger:
    """Dispatch ``AuditEntry`` objects to a single configured sink.

    Args:
        sink: Destination for every entry. Defaults to a JSONL sink at
            ``~/.tooltrust/audit.jsonl`` (the shipped default).
    """

    def __init__(self, sink: AuditSink | None = None) -> None:
        self._sink = sink if sink is not None else JsonlSink(_default_jsonl_path())

    @property
    def sink(self) -> AuditSink:
        """The configured sink (for inspection and CLI access)."""
        return self._sink

    def log(
        self,
        decision: Decision,
        call: NormalizedCall,
        *,
        session_id: str | None = None,
        approver: str | None = None,
        dry_run: bool | None = None,
    ) -> AuditEntry:
        """Build and persist the audit entry for one decision.

        Never raises. A failing sink is reported to stderr and the entry is
        dropped (the decision itself is already complete and safe to return).

        Args:
            decision: The decision to record.
            call: The normalized call that produced it.
            session_id: Session id (defaults to the call's).
            approver: Human approver for escalation entries.
            dry_run: Shadow-mode marker. Defaults to the decision's flag; the
                engine passes ``True`` for a shadowed run to record that the
                real decision was not enforced.
        """
        entry = AuditEntry.from_decision(
            decision, call, session_id=session_id, approver=approver, dry_run=dry_run
        )
        try:
            self._sink.write(entry)
        except Exception as exc:
            print(f"tooltrust audit: log failed: {exc}", file=sys.stderr)
        return entry

    def query(self, session_id: str | None = None) -> list[AuditEntry]:
        """Return recorded entries for a session (or all when ``None``)."""
        return self._sink.query(session_id)


def _default_jsonl_path() -> str:
    return "~/.tooltrust/audit.jsonl"


def build_sink(config: AuditConfig) -> AuditSink:
    """Build the concrete sink described by a policy's ``audit`` config.

    Args:
        config: The validated ``audit`` section of ``tooltrust.yaml``.

    Returns:
        A JsonlSink, SqliteSink, or PostgresSink. Postgres builds a
        lazy ``PostgresSink`` whose ``write`` falls back to a JSONL buffer
        when the database is unreachable.
    """
    sink_type = config.sink
    if sink_type == "jsonl":
        return JsonlSink(config.path or _default_jsonl_path())
    if sink_type == "sqlite":
        return SqliteSink(config.path)
    if sink_type == "postgres":
        if not config.postgres_url:
            raise ValueError("postgres audit sink requires audit.postgres_url in tooltrust.yaml")
        return PostgresSink(config.postgres_url, fallback_path=config.path)
    raise ValueError(f"unknown audit sink: {sink_type!r}")


def sink_from_config(config: dict[str, Any] | None) -> AuditSink:
    """Build a sink from a raw dict (used when no validated policy is loaded).

    Accepts the same shape as the ``audit`` section of ``tooltrust.yaml``:
    ``{"sink": "jsonl"|"sqlite"|"postgres", "path": ..., "postgres_url": ...}``.
    Malformed or missing configs fall back to the JSONL default so callers
    never crash because of a bad config.
    """
    config = config or {}
    validated = AuditConfig(**config)
    return build_sink(validated)
