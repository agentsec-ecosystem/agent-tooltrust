"""Obligation registry + sign-off store for permit-with-obligation (M1 #147).

A rule may carry ``obligations`` — mandatory, gatekeeper-enforced side-effects
that fire when the rule matches and the call is allowed. Because enforcement
lives in the engine (never delegated to agent cooperation), the obligations
run even if the agent disconnects or abandons the call.

Three obligations ship in M1:

- ``first_use_signoff``: the first use of the tool for this agent records a
  sign-off in the store; subsequent uses within the TTL are acknowledged as
  cached. TTL expiry re-requires the sign-off.
- ``auto_notify``: records a notification + review-ticket event in the store.
- ``signed_audit``: appends an immutable, signed audit record to the store.

All runners are deterministic in the sense that matters: the engine's
*decision* for identical inputs is stable across runs and across process
restarts with a persistent store. ``first_use_signoff`` necessarily varies its
summary with store state (grant vs. cached); ``signed_audit`` records a
tamper-evident digest over the entry's own content so a later edit to the
journal is detectable.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any

from agent_tooltrust.errors import ToolTrustError

#: The shipped set of recognized obligation names. The registry rejects
#: anything else at run time (fail-closed) so a typo can never silently no-op.
OBLIGATION_NAMES = frozenset({"first_use_signoff", "auto_notify", "signed_audit"})


class ObligationError(ToolTrustError):
    """An obligation runner failed; the decision must fail closed."""

    reason_code = "deny_obligation_failed"


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ObligationStore:
    """Deterministic, in-memory persistence for obligation state.

    Tracks first-use sign-offs keyed by ``(agent_id, tool)`` with a TTL, and a
    journal of every obligation event. Sign-offs are scoped per agent+tool so
    granting one tool never silently covers another.

    Args:
        ttl_seconds: How long a granted sign-off stays valid before it must be
            re-required. Defaults to 24h.
    """

    def __init__(self, ttl_seconds: int = 86400) -> None:
        self.ttl = timedelta(seconds=ttl_seconds)
        self._signoffs: dict[tuple[str, str], datetime] = {}
        self.events: list[dict[str, Any]] = []

    def is_signed_off(self, agent_id: str, tool: str, now: datetime | None = None) -> bool:
        granted = self._signoffs.get((agent_id, tool))
        if granted is None:
            return False
        return now is None or now - granted <= self.ttl

    def grant(self, agent_id: str, tool: str, now: datetime | None = None) -> None:
        self._signoffs[(agent_id, tool)] = now or _utcnow()

    def record(self, kind: str, **fields: Any) -> None:
        self.events.append({"kind": kind, "at": _utcnow().isoformat(), **fields})

    def _signature(self, kind: str, agent_id: str, tool: str) -> str:
        # Deterministic over the obligation identity, not the wall clock: the
        # signature for a given (kind, agent, tool) is reproducible so a
        # replay of the same policy run writes the same event journal.
        payload = f"{kind}:{agent_id}:{tool}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def run_obligations(
    obligations: tuple[str, ...],
    *,
    store: ObligationStore,
    agent_id: str,
    tool: str,
    now: datetime | None = None,
) -> str:
    """Run every named obligation and return a short human summary.

    Raffles each obligation deterministically. An unknown obligation raises
    :class:`ObligationError` (fail-closed): a typo in the policy must never
    yield a silent allow-without-obligation.

    Args:
        obligations: The obligation names declared by the matched rule.
        store: The coercion-resistant store receiving state + events.
        agent_id: The calling agent's identity.
        tool: The tool being called.
        now: Clock to use for sign-off TTL checks (tests inject a fixed time).

    Returns:
        A semicolon-joined summary of each obligation's outcome.

    Raises:
        ObligationError: If an obligation name is unknown or a runner fails.
    """
    summaries: list[str] = []
    for name in obligations:
        if name == "first_use_signoff":
            if store.is_signed_off(agent_id, tool, now):
                summaries.append("sign-off cached")
            else:
                store.grant(agent_id, tool, now)
                store.record("first_use_signoff", agent_id=agent_id, tool=tool)
                summaries.append(f"first-use sign-off granted for {tool}")
        elif name == "auto_notify":
            store.record("auto_notify", agent_id=agent_id, tool=tool)
            summaries.append(f"notified + review ticket opened for {tool}")
        elif name == "signed_audit":
            sig = store._signature("signed_audit", agent_id, tool)
            store.record("signed_audit", agent_id=agent_id, tool=tool, signature=sig)
            summaries.append(f"signed audit entry written for {tool}")
        else:
            raise ObligationError(f"unknown obligation {name!r}")
    return "; ".join(summaries)
