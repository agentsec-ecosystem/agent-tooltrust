"""M2 Task 1 — resource & environment scoping (DD-18, #145).

Policy scopes *which resources* a tool can touch, not just *which tool* runs.
Resources are namespaced by environment; a session declares a scope and any
call resolving outside it is denied. Scope is **default-deny**, not
default-open: an undeclared environment or resource tag is a deny, never a
pass-through.

The check is a pure function over a :class:`NormalizedCall` and a frozen
:class:`SessionScope`, so it is trivially testable and composable with the
engine's other pre-scoring gates (argument policy, obligations).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agent_tooltrust.types import NormalizedCall


@dataclass(frozen=True)
class SessionScope:
    """The environment + resource boundary a session may touch.

    A session is the execution context of one agent run. Declaring a scope
    pins that run to the named environments (and, optionally, resource tags).
    Any call whose environment — or resource tag, when tags are declared —
    falls outside the scope is denied before scoring (default-deny).

    Attributes:
        environments: Environment names the session may operate in. An
            empty set means *any* environment (unrestricted, e.g. a trusted
            orchestrator); a non-empty set is an allowlist.
        resource_tags: Optional allowlist of resource tags the session may
            touch. ``None`` (default) means no tag restriction; an empty
            tuple is *not* treated as "no restriction" — it forbids every
            tagged resource, so callers must choose deliberately.
    """

    environments: frozenset[str] = field(default_factory=frozenset)
    resource_tags: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        for env in self.environments:
            if not env.strip():
                raise ValueError("scope environments must be non-blank strings")


def scoping_violation(call: NormalizedCall, scope: SessionScope | None) -> str | None:
    """Return a human-readable violation reason, or ``None`` when in scope.

    ``None`` scope means no boundary was declared — the call is never
    rejected here (other gates still apply). A non-``None`` scope is
    default-deny: the first failing dimension produces the message.

    Args:
        call: The normalized call under evaluation.
        scope: The session scope in force, or ``None`` for unrestricted.

    Returns:
        A description of the first out-of-scope dimension, or ``None`` when
        the call is within scope.
    """
    if scope is None:
        return None
    if scope.environments and call.environment not in scope.environments:
        return (
            f"call environment {call.environment!r} outside session scope "
            f"{{{', '.join(sorted(scope.environments))}}}"
        )
    if scope.resource_tags is not None and call.resource_tag not in scope.resource_tags:
        return (
            f"call resource tag {call.resource_tag!r} outside session scope "
            f"tag list {scope.resource_tags!r}"
        )
    return None
