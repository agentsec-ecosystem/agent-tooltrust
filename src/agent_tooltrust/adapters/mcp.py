"""MCP client wrapper — proxy ``tools/call`` through the ToolTrust engine.

Wraps an MCP client's ``tools/call`` method so every invocation is evaluated
before the real tool executes. A deny decision is returned as an MCP error
(``isError: true``) with the reason as content, which MCP-native agents can
read and react to.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agent_tooltrust.adapters.base import BaseAdapter, CallContext
from agent_tooltrust.types import Decision


def _resolve_environment(arguments: dict[str, Any] | None) -> str:
    if arguments is None:
        return "production"
    return str(arguments.get("__tooltrust_environment", "production"))


def _resolve_data_class(arguments: dict[str, Any] | None) -> str:
    if arguments is None:
        return "internal"
    return str(arguments.get("__tooltrust_data_class", "internal"))


def _strip_meta(arguments: dict[str, Any] | None) -> dict[str, Any] | None:
    if arguments is None:
        return None
    return {k: v for k, v in arguments.items() if not k.startswith("__tooltrust_")}


class ToolTrustMCPWrapper(BaseAdapter):
    """Proxy an MCP client through the ToolTrust engine.

    Args:
        mcp_client: An MCP client with a ``tools/call`` method.
        engine: A configured Engine instance.
    """

    def __init__(self, mcp_client: Any, engine: Any) -> None:
        super().__init__(engine=engine)
        self._client = mcp_client

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

    def wrap_call(
        self, tool_name: str, arguments: dict[str, Any] | None = None
    ) -> Callable[..., Any]:
        """Return a callable that proxies ``tools/call`` through the engine.

        Args:
            tool_name: The MCP tool name being invoked.
            arguments: Tool arguments; ``__tooltrust_environment`` and
                ``__tooltrust_data_class`` keys are consumed for engine
                context and stripped before forwarding.

        Returns:
            A callable that evaluates the call and then delegates to the
            underlying MCP client, returning an MCP result or an MCP error.
        """
        env = _resolve_environment(arguments)
        data_cls = _resolve_data_class(arguments)
        clean_args = _strip_meta(arguments)

        ctx = CallContext(
            tool_name=tool_name,
            action="call",
            environment=env,
            data_class=data_cls,
            agent_id="mcp-client",
            arguments=clean_args,
        )

        decision = self.intercept(ctx)

        if decision.decision in ("deny", "escalate"):
            return lambda: {
                "isError": True,
                "content": [
                    {
                        "type": "text",
                        "text": f"[ToolTrust] {decision.decision}: {decision.explanation}",
                    }
                ],
            }

        original_call = self._client.tools.call
        return lambda: original_call(tool_name, clean_args)
