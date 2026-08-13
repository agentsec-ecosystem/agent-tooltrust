"""Raw Python adapter — ``@engine.guard`` decorator and session context manager.

The simplest integration path: import :class:`~agent_tooltrust.engine.engine.Engine`,
wrap any Python callable with ``@engine.guard``, and the engine evaluates before
the function body runs. A deny decision raises :class:`ToolTrustDecisionError` so
the caller can handle it as a native Python exception.

The context manager ``engine.session(agent_id=..., session_id=...)`` tags every
guarded call inside its body with the same agent and session identity, avoiding
repetition.
"""

from __future__ import annotations

import contextvars
import functools
from collections.abc import Callable
from typing import Any

from agent_tooltrust.adapters.base import BaseAdapter, CallContext
from agent_tooltrust.types import Decision


class ToolTrustDecisionError(Exception):
    """Raised when the engine denies or requires escalation for a guarded call.

    Attributes:
        decision: The full Decision returned by the engine.
    """

    def __init__(self, decision: Decision) -> None:
        self.decision = decision
        super().__init__(
            f"[ToolTrust] {decision.decision}: {decision.explanation} ({decision.reason_code})"
        )


_current_session: contextvars.ContextVar[dict[str, str] | None] = contextvars.ContextVar(
    "tooltrust_session", default=None
)


class RawAdapter(BaseAdapter):
    """Intercept plain Python callables via :class:`~agent_tooltrust.engine.engine.Engine`.

    Args:
        engine: A configured Engine instance.
    """

    def intercept(self, ctx: CallContext) -> Decision:
        return self.engine.evaluate(
            tool_name=ctx.tool_name,
            action=ctx.action,
            environment=ctx.environment,
            data_class=ctx.data_class,
            agent_id=ctx.agent_id,
            arguments=ctx.arguments,
            context=ctx.context,
        )

    def guard(
        self,
        *,
        tool_name: str = "",
        action: str = "",
        environment: str = "production",
        data_class: str = "internal",
        agent_id: str = "",
        session_id: str | None = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator that evaluates a call through the engine before executing.

        Args:
            tool_name: Tool identity for the engine (defaults to function name).
            action: Action being performed (defaults to ``"call"``).
            environment: Deployment environment.
            data_class: Data sensitivity label.
            agent_id: Agent identity (defaults to the active session's agent).
            session_id: Session identity (defaults to the active session).

        Returns:
            A decorator that wraps a callable.
        """

        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            name = tool_name or fn.__name__

            @functools.wraps(fn)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                session = _current_session.get() or {}
                resolved_agent = agent_id or session.get("agent_id", "unknown")
                resolved_session = session_id or session.get("session_id")

                ctx = CallContext(
                    tool_name=name,
                    action=action or "call",
                    environment=environment,
                    data_class=data_class,
                    agent_id=resolved_agent,
                    session_id=resolved_session,
                    arguments=kwargs or None,
                )
                decision = self.intercept(ctx)
                if decision.decision in ("deny", "escalate"):
                    raise ToolTrustDecisionError(decision)
                return fn(*args, **kwargs)

            return wrapper

        return decorator

    def session(
        self,
        *,
        agent_id: str = "",
        session_id: str | None = None,
    ) -> Any:
        """Context manager that tags every guarded call inside its body.

        Args:
            agent_id: Default agent identity for the block.
            session_id: Default session identity for the block.
        """

        class Session:
            def __enter__(self) -> Session:
                self._token = _current_session.set(
                    {"agent_id": agent_id, "session_id": session_id or ""}
                )
                return self

            def __exit__(self, *exc: object) -> None:
                _current_session.reset(self._token)

        return Session()
