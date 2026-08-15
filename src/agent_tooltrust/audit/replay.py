"""M5 Task 1 (#81) — session replay from the audit trail.

Reconstructs a session's cumulative state from its audit entries alone, so an
operator can answer "what actually happened in this session" without re-running
the engine — and so a session tracked by a live ``SessionStore`` can be
cross-checked against the persisted record.

Two signal guarantees make the replay authoritative:

* **Ordering** — entries are sorted by timestamp (stable, so equal timestamps
  keep their audit-write order). A replay is therefore identical on JSONL,
  SQLite, and Postgres sinks no matter what order the backend returns rows.
* **Cumulative risk** — per-call risk uses the same falloff rule as the live
  ``SessionStore`` (``session_risk_increment``), so the replayed cumulative
  risk at every step matches ``SessionStore.risk_score`` after the same call
  sequence. Denied calls add no risk, exactly like the store.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agent_tooltrust.audit.models import AuditEntry
from agent_tooltrust.engine.explain import session_risk_increment

#: Decision values that count as "accepted" (i.e. they accrue session risk).
_ACCEPTED = frozenset({"allow", "audit", "escalate", "allow_with_obligation"})


@dataclass(frozen=True)
class ReplayPoint:
    """One reconstructed decision inside a replayed session.

    Attributes:
        index: 1-based position in the session (chronological).
        call_id: The audit entry's call id.
        timestamp: ISO-8601 timestamp of the entry.
        tool: The tool that was called.
        action: The action verb.
        decision: The decision value (allow/audit/escalate/deny/...).
        criticality: The decision's severity.
        reason_code: The canonical reason for the decision.
        risk_increment: Risk this call added to the session (0 for denies).
        cumulative_risk: ``SessionStore.risk_score`` after this call (running).
        call_count: Tool calls accepted so far, including this one.
        dry_run: Whether this entry was recorded in shadow mode.
    """

    index: int
    call_id: str
    timestamp: str
    tool: str
    action: str
    decision: str
    criticality: str
    reason_code: str
    risk_increment: float
    cumulative_risk: float
    call_count: int
    dry_run: bool

    def to_dict(self) -> dict[str, Any]:
        """JSON-friendly representation of this replay point."""
        return {
            "index": self.index,
            "call_id": self.call_id,
            "timestamp": self.timestamp,
            "tool": self.tool,
            "action": self.action,
            "decision": self.decision,
            "criticality": self.criticality,
            "reason_code": self.reason_code,
            "risk_increment": self.risk_increment,
            "cumulative_risk": self.cumulative_risk,
            "call_count": self.call_count,
            "dry_run": self.dry_run,
        }


@dataclass(frozen=True)
class SessionReplay:
    """The reconstructed state of one session from its audit entries.

    Attributes:
        session_id: The replayed session id.
        points: One :class:`ReplayPoint` per entry, in chronological order.
        call_count: Total tool calls recorded for the session.
        deny_count: How many of those calls were denied.
        cumulative_risk: Final ``SessionStore.risk_score`` for the session.
        denies: Shorthand list of the denied call ids (for ``--replay`` output).
    """

    session_id: str | None
    points: list[ReplayPoint] = field(default_factory=list)
    call_count: int = 0
    deny_count: int = 0
    cumulative_risk: float = 0.0
    denies: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """JSON-friendly summary + the full chronological replay."""
        return {
            "session_id": self.session_id,
            "call_count": self.call_count,
            "deny_count": self.deny_count,
            "cumulative_risk": self.cumulative_risk,
            "denied_call_ids": self.denies,
            "points": [p.to_dict() for p in self.points],
        }


def replay_session(entries: list[AuditEntry], session_id: str | None = None) -> SessionReplay:
    """Reconstruct a session's cumulative state from its audit entries.

    Args:
        entries: The audit entries for the session, in any order. They are
            sorted chronologically (stable) before reconstruction.
        session_id: The session id to report. Defaults to the first entry's
            ``session_id``, or ``None`` for an empty replay.

    Returns:
        A :class:`SessionReplay` whose ``points`` match the cumulative risk a
        live ``SessionStore`` would have produced for the same call sequence.
    """
    ordered = sorted(entries, key=lambda e: e.timestamp)
    if session_id is None:
        session_id = ordered[0].session_id if ordered else None

    points: list[ReplayPoint] = []
    cumulative = 0.0
    accepted = 0
    deny_count = 0
    denies: list[str] = []
    for index, entry in enumerate(ordered, start=1):
        increment = (
            session_risk_increment(entry.criticality)
            if entry.decision in _ACCEPTED
            else 0.0
        )
        if increment > 0.0:
            accepted += 1
            cumulative += increment
        if entry.decision == "deny":
            deny_count += 1
            denies.append(entry.call_id)
        points.append(
            ReplayPoint(
                index=index,
                call_id=entry.call_id,
                timestamp=entry.timestamp,
                tool=entry.tool,
                action=entry.action,
                decision=entry.decision,
                criticality=entry.criticality,
                reason_code=entry.reason_code,
                risk_increment=increment,
                cumulative_risk=cumulative,
                call_count=accepted,
                dry_run=entry.dry_run,
            )
        )

    return SessionReplay(
        session_id=session_id,
        points=points,
        call_count=len(ordered),
        deny_count=deny_count,
        cumulative_risk=cumulative,
        denies=denies,
    )


__all__ = ["ReplayPoint", "SessionReplay", "replay_session"]
