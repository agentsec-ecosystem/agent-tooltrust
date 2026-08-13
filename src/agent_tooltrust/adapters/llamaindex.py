"""LlamaIndex adapter — ``wrap_tool`` that guards a ``FunctionTool``.

LlamaIndex agents execute tools built with ``FunctionTool.from_defaults`` (a
callable plus schema). This adapter wraps a tool's underlying function so every
invocation passes through the ToolTrust engine. A deny decision raises
:class:`ToolTrustDecisionError`, which LlamaIndex surfaces as a tool error the
agent can handle.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any

from agent_tooltrust.adapters.base import BaseAdapter, CallContext
from agent_tooltrust.adapters.raw import ToolTrustDecisionError
from agent_tooltrust.types import Decision


class LlamaIndexAdapter(BaseAdapter):
    """Guard LlamaIndex tools with ToolTrust evaluation.

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
        """Wrap a LlamaIndex tool function so it is guarded by ToolTrust.

        Pass the result to ``FunctionTool.from_defaults``.

        Args:
            tool_fn: The tool function to guard.
            tool_name: Tool identity (defaults to the function name).
            action: Action (defaults to ``"call"``).
            environment: Deployment environment.
            data_class: Data sensitivity label.
            agent_id: Agent identity.

        Returns:
            A wrapped callable that evaluates through the engine before
            delegating to *tool_fn*.
        """
        name = tool_name or getattr(tool_fn, "__name__", "unknown")

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

        return guarded
