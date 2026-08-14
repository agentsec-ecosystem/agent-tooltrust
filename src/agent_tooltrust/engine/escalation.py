"""M3 — EscalationManager: human-in-the-loop approval round-trip (F-09/F-90).

A call that resolves to ``escalate`` needs a human decision before it may run.
This manager is the single source of truth for that round-trip:

- :meth:`create` records a pending escalation bound to an **action_identity**
  (a deterministic hash of tool + action + arguments, F-09) and a TTL.
- :meth:`approve` binds the approval to that exact action identity and records
  the approver, so the approval cannot be replayed for a different call.
- :meth:`deny` records the denial with the approver and a reason.
- :meth:`resolve` consults the record: approved + in-TTL => execute; denied or
  expired => deny; unknown / already-resolved => deny.

Replay safety (F-89-P1, #95): the same ``escalation_id`` may only be resolved
against the exact call it was created for. A re-submission with different
tool/action/args yields ``DENY_ACTION_IDENTITY_MISMATCH`` or
``DENY_ESCALATION_REPLAY``.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

from agent_tooltrust.types import NormalizedCall


class EscalationStatus(Enum):
    """Lifecycle of an escalation record."""

    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"


@dataclass(frozen=True)
class Escalation:
    """One recorded escalation request.

    Attributes:
        escalation_id: Unique, unguessable id used in approve/deny/resolve.
        status: Current lifecycle state.
        action: The action verb (e.g. ``"deploy"``).
        tool: The tool name the agent called.
        agent_id: The calling agent identity.
        environment: The call's environment.
        data_class: The call's data class.
        arguments: The call's arguments (frozen for identity hashing).
        reason: The render explanation that triggered escalation.
        action_identity: Deterministic hash of (tool, action, arguments).
        created_at: ISO-8601 UTC creation time.
        expires_at: ISO-8601 UTC expiry (TTL) time.
        approver: Human who approved/denied, once resolved.
        denied_reason: Human reason, when denied.
    """

    escalation_id: str
    status: EscalationStatus
    tool: str
    action: str
    agent_id: str
    environment: str
    data_class: str
    action_identity: str
    reason: str
    arguments: dict[str, Any]
    created_at: str
    expires_at: str
    approver: str | None = None
    denied_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """JSON-friendly representation for the CLI and web dashboard."""
        return {
            "escalation_id": self.escalation_id,
            "status": self.status.value,
            "tool": self.tool,
            "action": self.action,
            "agent_id": self.agent_id,
            "environment": self.environment,
            "data_class": self.data_class,
            "action_identity": self.action_identity,
            "reason": self.reason,
            "arguments": self.arguments,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "expired": self.is_expired(),
            "approver": self.approver,
            "denied_reason": self.denied_reason,
        }

    def is_expired(self, now: datetime | None = None) -> bool:
        """Whether the escalation has outlived its TTL (treated as deny)."""
        check = now or _utcnow()
        return check > _parse_iso(self.expires_at)


def _utcnow() -> datetime:
    """Return the current UTC time."""
    return datetime.now(UTC)


def _parse_iso(value: str) -> datetime:
    """Parse an ISO-8601 UTC timestamp back to a datetime."""
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def action_identity(tool: str, action: str, arguments: dict[str, Any] | None) -> str:
    """Deterministic SHA-256 fingerprint of (tool, action, arguments).

    This is F-09's "approval is bound to an action identity": two calls that
    differ in tool, action, or argument content hash to different identities,
    so an approval minted for one cannot be replayed onto another.

    Args:
        tool: The tool name.
        action: The action verb.
        arguments: The call arguments (or ``None``).

    Returns:
        A 16-hex-char prefix of the SHA-256 digest.
    """
    payload = f"{tool}\u0000{action}\u0000{_canonical_args(arguments)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _canonical_args(arguments: dict[str, Any] | None) -> str:
    """Normalize arguments into a stable string for hashing.

    ``None`` (no arguments were provided) and an explicit empty dict are
    distinguished so a call that carries no arguments is treated differently
    from one that passes an empty argument set. Nested dicts/lists are
    flattened with sorted keys so logically identical argument dicts hash the
    same regardless of insertion order.
    """
    if arguments is None:
        return "<none>"
    if not arguments:
        return "<empty>"
    if isinstance(arguments, dict):
        items = []
        for key in sorted(arguments):
            items.append(f"{key}={_canonical_args(arguments[key])}")
        return "{" + ",".join(items) + "}"
    if isinstance(arguments, (list, tuple)):
        return "[" + ",".join(_canonical_args(v) for v in arguments) + "]"
    return str(arguments)


class EscalationManager:
    """Track escalation records and enforce approve/deny/expire + replay.

    Args:
        ttl_seconds: Default approval TTL in seconds (default 300 = 5 min).
    """

    def __init__(self, ttl_seconds: int = 300) -> None:
        self.ttl = timedelta(seconds=ttl_seconds)
        self._records: dict[str, Escalation] = {}
        self._events: list[dict[str, Any]] = []
        self._identity_index: dict[str, str] = {}

    @property
    def records(self) -> dict[str, Escalation]:
        """Read-only view of all escalation records (id -> record)."""
        return dict(self._records)

    def pending(self, now: datetime | None = None) -> list[Escalation]:
        """Return unresolved (pending) escalations in creation order."""
        return [r for r in self._records.values() if r.status == EscalationStatus.PENDING]

    def create(self, call: NormalizedCall, *, reason: str = "",
               now: datetime | None = None) -> Escalation:
        """Create a new pending escalation for a call that resolved to escalate.

        Args:
            call: The normalized call that triggered escalation.
            reason: Human-readable reason for the approval request.
            now: Clock for TTL computation (tests inject a fixed time).

        Returns:
            The new pending :class:`Escalation` bound to the call's
            action identity.
        """
        now = now or _utcnow()
        escalation = Escalation(
            escalation_id="esc_" + secrets.token_hex(8),
            status=EscalationStatus.PENDING,
            tool=call.tool,
            action=call.action,
            agent_id=call.agent_id,
            environment=call.environment,
            data_class=call.data_class,
            action_identity=action_identity(call.tool, call.action, call.arguments),
            reason=reason,
            arguments=call.arguments or {},
            created_at=now.isoformat(),
            expires_at=(now + self.ttl).isoformat(),
        )
        self._records[escalation.escalation_id] = escalation
        self._record_event("created", escalation)
        return escalation

    def attest(self, escalation_id: str, *, call: NormalizedCall,
               now: datetime | None = None) -> Escalation:
        """Bind an approval/deny attestation to the *exact* call.

        Rejects the id when it is unknown or already resolved (replay), and
        returns ``DENY_ACTION_IDENTITY_MISMATCH`` when the provided call does
        not match the escalation's bound action identity.

        Args:
            escalation_id: The escalation being acted on.
            call: The call being approved/denied upfront.

        Returns:
            The matched :class:`Escalation` when it is still pending and the
            call matches. ``None`` here signals a conflict to the caller.

        Raises:
            ValueError: Unknown or already-resolved escalation, or action
                identity mismatch.
        """
        record = self._records.get(escalation_id)
        if record is None:
            raise ValueError("unknown escalation_id")
        if record.status != EscalationStatus.PENDING:
            raise ValueError(f"escalation already resolved as {record.status.value}")
        if record.is_expired(now):
            self._expire(record, now)
            raise ValueError("escalation expired")
        incoming = action_identity(call.tool, call.action, call.arguments)
        if incoming != record.action_identity:
            raise ValueError("action identity mismatch")
        return record

    def approve(self, escalation_id: str, *, approver: str,
                now: datetime | None = None) -> Escalation:
        """Approve a pending escalation (the agent may execute).

        Args:
            escalation_id: The escalation to approve.
            approver: Human identity who approved.
            now: Clock (tests inject a fixed time).

        Returns:
            The approved :class:`Escalation`.

        Raises:
            ValueError: Unknown, already-resolved, or expired escalation; or
                a blank approver.
        """
        if not approver or not approver.strip():
            raise ValueError("approver must be a non-blank string")
        record = self._records.get(escalation_id)
        if record is None:
            raise ValueError("unknown escalation_id")
        if record.status != EscalationStatus.PENDING:
            raise ValueError(f"escalation already resolved as {record.status.value}")
        if record.is_expired(now):
            self._expire(record, now)
            raise ValueError("escalation expired")
        approved = _with(record, status=EscalationStatus.APPROVED, approver=approver)
        self._records[escalation_id] = approved
        self._record_event("approved", approved)

        # When an approval is consumed, key the record by its action identity
        # so a later re-submission of the same call can be matched to it.
        self._identity_index[approved.action_identity] = approved.escalation_id
        return approved

    def deny(self, escalation_id: str, *, approver: str, reason: str = "",
             now: datetime | None = None) -> Escalation:
        """Deny a pending escalation (the agent must not execute).

        Args:
            escalation_id: The escalation to deny.
            approver: Human identity who denied.
            reason: Optional human-readable denial reason.
            now: Clock (tests inject a fixed time).

        Returns:
            The denied :class:`Escalation`.

        Raises:
            ValueError: Unknown, already-resolved, or expired escalation; or
                a blank approver.
        """
        if not approver or not approver.strip():
            raise ValueError("approver must be a non-blank string")
        record = self._records.get(escalation_id)
        if record is None:
            raise ValueError("unknown escalation_id")
        if record.status != EscalationStatus.PENDING:
            raise ValueError(f"escalation already resolved as {record.status.value}")
        if record.is_expired(now):
            self._expire(record, now)
            raise ValueError("escalation expired")
        denied = _with(
            record, status=EscalationStatus.DENIED, approver=approver,
            denied_reason=reason or None,
        )
        self._records[escalation_id] = denied
        self._record_event("denied", denied)
        return denied

    def resolve(self, escalation_id: str, *, call: NormalizedCall,
                now: datetime | None = None) -> dict[str, Any]:
        """Resolve an escalation for a call: approve => execute, else deny.

        This is the engine-facing entry point. It enforces replay safety
        (same id reused for a different call) and TTL expiry.

        Args:
            escalation_id: The escalation being re-submitted by the agent.
            call: The call being attempted.
            now: Clock (tests inject a fixed time).

        Returns:
            A dict ``{"status": <str>, "reason_code": <str>, "explanation": <str>}``
            describing whether the call may execute.
        """
        record = self._records.get(escalation_id)
        if record is None:
            return {
                "status": "deny",
                "reason_code": "deny_escalation_unknown",
                "explanation": f"unknown escalation {escalation_id!r}",
            }
        if record.is_expired(now):
            self._expire(record, now)
            return {
                "status": "deny",
                "reason_code": "deny_escalation_expired",
                "explanation": f"escalation {escalation_id} approval expired",
            }
        incoming = action_identity(call.tool, call.action, call.arguments)
        if incoming != record.action_identity:
            return {
                "status": "deny",
                "reason_code": "deny_action_identity_mismatch",
                "explanation": (
                    f"escalation {escalation_id} was approved for a different "
                    "tool/action/argument set"
                ),
            }
        if record.status == EscalationStatus.APPROVED:
            return {
                "status": "allow",
                "reason_code": "allow_escalation_approved",
                "explanation": "escalation approved; call may execute",
            }
        if record.status == EscalationStatus.DENIED:
            return {
                "status": "deny",
                "reason_code": "deny_escalation_denied",
                "explanation": record.denied_reason or "escalation denied",
            }
        return {
            "status": "deny",
            "reason_code": "deny_escalation_replay",
            "explanation": "escalation is still pending and was not approved",
        }

    def find_by_action_identity(self, action_identity: str) -> str | None:
        """Return the approved escalation id bound to an action identity."""
        return self._identity_index.get(action_identity)

    def _expire(self, record: Escalation, now: datetime | None = None) -> None:
        self._records[record.escalation_id] = _with(record, status=EscalationStatus.EXPIRED)
        self._record_event("expired", record)

    def _record_event(self, kind: str, record: Escalation) -> None:
        self._events.append({"kind": kind, "id": record.escalation_id, "at": _utcnow().isoformat()})


def _with(record: Escalation, **changes: Any) -> Escalation:
    """Return a new Escalation with the given field changes applied."""
    return replace(record, **changes)
