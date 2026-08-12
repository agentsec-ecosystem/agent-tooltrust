"""AutoGen / AG2 adapter — ``wrap_tool`` that guards tool callables.

AutoGen agents execute functions registered as tools (often async). This
adapter wraps any such callable so every invocation passes through the
ToolTrust engine. A deny decision raises :class:`ToolTrustDecisionError`,
which AutoGen surfaces as a tool error the model can read and react to.
"""

from __future__ import annotations

import functools
import inspect
from collections.abc import Callable
from typing import Any

from agent_tooltrust.adapters.base import BaseAdapter, CallContext
from agent_tooltrust.adapters.raw import ToolTrustDecisionError
from agent_tooltrust.types import Decision


class AutoGenAdapter(BaseAdapter):
    """Guard AutoGen / AG2 tool callables with ToolTrust evaluation.

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

    def wrap_tool(
        self,
        tool_fn: Callable[..., Any],
        *,
        tool_name: str = "",
        action: str = "",
        environment: str = "production",
        data_class: str = "internal",
        agent_id: str = "",
    ) -> Callable[..., Any]:
        """Wrap an AutoGen tool callable so it is guarded by ToolTrust.

        Args:
            tool_fn: The tool callable to guard.
            tool_name: Tool identity (defaults to the callable name).
            action: Action (defaults to ``"call"``).
            environment: Deployment environment.
            data_class: Data sensitivity label.
            agent_id: Agent identity.

        Returns:
            A wrapped callable (async-aware) that evaluates through the
            engine before delegating to *tool_fn*.
        """
        name = tool_name or getattr(tool_fn, "__name__", "unknown")
        is_async = inspect.iscoroutinefunction(tool_fn)

        @functools.wraps(tool_fn)
        def guarded(*args: Any, **kwargs: Any) -> Any:
            ctx = CallContext(
                tool_name=name,
                action=action or "call",
                environment=environment,
                data_class=data_class,
                agent_id=agent_id,
                arguments=kwargs or None,
            )
            decision = self.intercept(ctx)
            if decision.decision in ("deny", "escalate"):
                raise ToolTrustDecisionError(decision)
            return tool_fn(*args, **kwargs)

        if is_async:

            @functools.wraps(tool_fn)
            async def guarded_async(*args: Any, **kwargs: Any) -> Any:
                ctx = CallContext(
                    tool_name=name,
                    action=action or "call",
                    environment=environment,
                    data_class=data_class,
                    agent_id=agent_id,
                    arguments=kwargs or None,
                )
                decision = self.intercept(ctx)
                if decision.decision in ("deny", "escalate"):
                    raise ToolTrustDecisionError(decision)
                return await tool_fn(*args, **kwargs)

            return guarded_async

        return guarded
