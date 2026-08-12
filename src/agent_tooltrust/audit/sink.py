"""The ``AuditSink`` interface — two methods, any backing store.

A sink appends entries and answers session queries. Both operations are
best-effort: a failing sink must log to stderr (or raise a
:class:`SinkError`, which the logger facade converts to stderr) and must
never be the thing that breaks a decision.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from agent_tooltrust.audit.models import AuditEntry


class AuditSinkError(RuntimeError):
    """A sink could not write or query entries.

    Raised so the ``AuditLogger`` facade can convert it to a stderr warning.
    """


class AuditSink(ABC):
    """Pluggable destination for audit entries.

    Implement ``write`` to persist one entry and ``query`` to return every
    entry for a session (or all entries when *session_id* is ``None``).
    """

    @abstractmethod
    def write(self, entry: AuditEntry) -> None:
        """Append one audit entry. Never raise on persistence failure."""

    @abstractmethod
    def query(self, session_id: str | None = None) -> list[AuditEntry]:
        """Return entries for *session_id*, or all entries when ``None``."""
