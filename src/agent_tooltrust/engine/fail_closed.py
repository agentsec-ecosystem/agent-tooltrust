"""M1.6 — fail-closed safety net.

Every engine failure path maps to a deny decision with a machine-readable
reason_code. A failure is never allowed to leak through as an allow.
"""

import functools
from collections.abc import Callable
from typing import Any, TypeVar

from agent_tooltrust.errors import ToolTrustError
from agent_tooltrust.types import Decision

F = TypeVar("F", bound=Callable[..., Any])


def deny(
    reason_code: str,
    message: str,
    policy_version: str = "0.0.0",
) -> Decision:
    """Build a deny Decision for a reason outside the normal band logic.

    Used by the fail-closed handler and available to callers that need to
    build an explicit deny (e.g. a wrapper that rejects a call before the
    engine runs). Always a critical-severity deny with empty factors and no
    escalation id — the reason_code and message are the only signal.
    """
    return Decision(
        decision="deny",
        criticality="critical",
        reason_code=reason_code,
        explanation=message,
        factors=[],
        escalation_id=None,
        dry_run=False,
        policy_version=policy_version,
    )


def fail_closed(func: F) -> F:
    """Wrap ``func`` so any ToolTrustError becomes a deny Decision.

    This is the safety axiom of the engine: no matter what stage fails — a
    malformed call, an unknown tool, a broken policy, a dead backend — the
    caller receives a deny, never an allow and never a crash. Only the
    toolbox's own exceptions (``ToolTrustError`` and subclasses) are
    converted; an unexpected ``TypeError``/``ValueError``/``KeyError`` is
    re-raised so genuine bugs are not masked by a fake deny.
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except ToolTrustError as exc:
            return deny(exc.reason_code, str(exc))

    return wrapper  # type: ignore[return-value]
