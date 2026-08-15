"""M2 Task 2 — child-agent delegation (F-88, #108).

A parent agent may delegate work to a child agent, but the child's scope must
be a **subset** of the parent's scope. This is the confused-deputy protection:
a parent cannot mint a child that can reach further than the parent itself
could. A delegation that would exceed the parent's scope is denied.

The manager keeps an audit-friendly registry of every delegation (the
parent→child chain) so the trail can show who spawned whom.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from agent_tooltrust.errors import (
    DENY_DELEGATION_EXCEEDS_SCOPE,
    DENY_DELEGATION_UNKNOWN_PARENT,
)
from agent_tooltrust.policy.models import AgentProfile, Policy


def _utc_now() -> str:
    """ISO-8601 UTC timestamp for delegation records."""
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class Delegation:
    """One recorded parent→child delegation.

    ``environments`` is the child's allowed environment scope (a subset of the
    parent's). Retaining it on the record makes the chain self-contained for
    the audit trail without needing to re-read the policy.

    Attributes:
        child_id: The delegated (child) agent identity.
        parent_id: The delegating parent agent identity.
        environments: The child's allowed environments (parent-scope subset).
        timestamp: ISO-8601 UTC time the delegation was recorded.
    """

    child_id: str
    parent_id: str
    environments: tuple[str, ...]
    timestamp: str


@dataclass(frozen=True)
class DelegationResult:
    """Outcome of a delegation attempt.

    Attributes:
        allowed: ``True`` when the delegation was registered, ``False`` when
            it was denied (unknown parent, or child scope exceeding parent).
        reason_code: Machine-readable outcome code.
        explanation: Human-readable description of the outcome.
        delegation: The registered :class:`Delegation` on success, else ``None``.
    """

    allowed: bool
    reason_code: str
    explanation: str
    delegation: Delegation | None = None


class DelegationManager:
    """Enforce the child-scope-⊆-parent-scope invariant and record the chain.

    Thread-safe enough for a single engine: the registry is only mutated by
    :meth:`delegate`, and reads (:meth:`delegation_chain`) are stable snapshots.
    """

    def __init__(self) -> None:
        self._delegations: dict[str, Delegation] = {}
        self._children_by_parent: dict[str, list[str]] = {}

    @property
    def delegations(self) -> dict[str, Delegation]:
        """A read-only view of all recorded delegations (child_id → record)."""
        return dict(self._delegations)

    def delegate(
        self,
        child_id: str,
        parent_id: str,
        policy: Policy,
        environments: tuple[str, ...] = (),
    ) -> DelegationResult:
        """Register a child delegation, enforcing the scope-subset invariant.

        The child's requested ``environments`` must be a subset of the
        parent's own allowed environments (from ``policy``). A parent with an
        empty (unrestricted) scope may delegate any non-superset scope; a
        parent restricted to ``("staging",)`` may not mint a child that can
        reach ``("staging", "production")``.

        ``parent_id`` must resolve to a concrete agent in ``policy.agents`` —
        it may not fall back to the default agent, because that would let a
        caller mint a child from an unprivileged unknown identity.

        Args:
            child_id: The identity being created by this delegation.
            parent_id: The existing identity that authorizes the delegation.
            policy: The policy whose agent registry holds the parent's scope.
            environments: The child's requested scroll environments.

        Returns:
            A :class:`DelegationResult` describing allow or deny.
        """
        parent = policy.agents.get(parent_id)
        if parent is None:
            return DelegationResult(
                allowed=False,
                reason_code=DENY_DELEGATION_UNKNOWN_PARENT,
                explanation=f"cannot delegate: unknown parent identity {parent_id!r}",
            )

        if not self._is_subset(environments, parent):
            return DelegationResult(
                allowed=False,
                reason_code=DENY_DELEGATION_EXCEEDS_SCOPE,
                explanation=(
                    f"child scope {sorted(environments)!r} exceeds parent "
                    f"{parent_id!r} scope {sorted(parent.environments)!r}"
                ),
            )

        delegation = Delegation(
            child_id=child_id,
            parent_id=parent_id,
            environments=tuple(sorted(environments)),
            timestamp=_utc_now(),
        )
        self._delegations[child_id] = delegation
        self._children_by_parent.setdefault(parent_id, []).append(child_id)
        return DelegationResult(
            allowed=True,
            reason_code="allow_delegation",
            explanation=f"delegated {child_id!r} under parent {parent_id!r}",
            delegation=delegation,
        )

    def child_ids_of(self, parent_id: str) -> tuple[str, ...]:
        """Return the direct children a parent has spawned, sorted."""
        return tuple(sorted(self._children_by_parent.get(parent_id, ())))

    def delegation_chain(self, child_id: str) -> tuple[str, ...]:
        """Return the parent lineage of *child_id* (child → root).

        Walks ``child.parent`` fields, resolving each parent through the
        registry's recorded parents. When an ancestor is not itself a
        registered delegation (a top-level policy agent), the chain stops at
        the nearest known parent.

        Args:
            child_id: The identity to trace.

        Returns:
            Ordered chain ``(child_id, parent_id, grandparent_id, ...)``.
        """
        chain: list[str] = []
        seen: set[str] = set()
        current: str | None = child_id
        while current is not None and current not in seen:
            seen.add(current)
            chain.append(current)
            delegation = self._delegations.get(current)
            current = delegation.parent_id if delegation else None
        return tuple(chain)

    @staticmethod
    def _is_subset(requested: tuple[str, ...], parent: AgentProfile) -> bool:
        """A child scope is a subset of the parent's when parent is unrestricted."""
        if not parent.environments:
            return True
        return set(requested) <= set(parent.environments)
