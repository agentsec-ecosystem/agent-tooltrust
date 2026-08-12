"""Smolagents adapter — ``wrap_tool`` that guards a smolagents ``Tool``.

Smolagents agents execute tools defined with ``@tool`` (a ``Tool`` subclass
whose ``forward`` runs the body). This adapter wraps a ``Tool`` instance so
every invocation passes through the ToolTrust engine. A deny decision returns
an error string as the tool output, which the agent can read and react to.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agent_tooltrust.adapters.base import BaseAdapter, CallContext
from agent_tooltrust.types import Decision


class SmolagentsAdapter(BaseAdapter):
    """Guard smolagents tools with ToolTrust evaluation.

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
        tool: Any,
        *,
        tool_name: str = "",
        action: str = "",
        environment: str = "production",
        data_class: str = "internal",
        agent_id: str = "",
    ) -> Any:
        """Wrap a smolagents ``Tool`` so its ``forward`` is guarded.

        Args:
            tool: A smolagents Tool instance with a ``forward`` method and a
                ``name`` attribute.
            tool_name: Tool identity (defaults to the tool's name attribute).
            action: Action (defaults to ``"call"``).
            environment: Deployment environment.
            data_class: Data sensitivity label.
            agent_id: Agent identity.

        Returns:
            The tool with ``forward`` replaced by a guarded version.
        """
        name = tool_name or getattr(tool, "name", "unknown")
        original_forward: Callable[..., Any] = tool.forward

        def guarded_forward(*args: Any, **kwargs: Any) -> Any:
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
                return f"[ToolTrust] {decision.decision}: {decision.explanation}"
            return original_forward(*args, **kwargs)

        tool.forward = guarded_forward
        return tool
