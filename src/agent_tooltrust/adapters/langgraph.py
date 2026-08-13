"""LangGraph adapter — ``ToolTrustToolNode`` that evaluates before execution.

Subclasses LangGraph's ``ToolNode`` and overrides ``_run_one()`` so that every
tool invocation passes through the ToolTrust engine. A deny decision returns a
``ToolMessage`` with the reason as content, allowing the agent graph to continue
without crashing.
"""

from __future__ import annotations

from typing import Any, cast

from agent_tooltrust.adapters.base import BaseAdapter, CallContext
from agent_tooltrust.types import Decision


class ToolTrustToolNode(BaseAdapter):
    """A LangGraph ``ToolNode`` that evaluates every call through ToolTrust.

    Args:
        tools: A list of LangChain tools to wrap.
        engine: A configured Engine instance.
        agent_id: Identity of the agent making calls.
        environment: Deployment environment label.
        data_class: Data sensitivity label.
    """

    def __init__(
        self,
        tools: list[Any],
        engine: Any,
        *,
        agent_id: str = "",
        environment: str = "production",
        data_class: str = "internal",
    ) -> None:
        super().__init__(engine=engine)
        self._tools = tools
        self._agent_id = agent_id
        self._environment = environment
        self._data_class = data_class

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

    def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        try:
            from langgraph.prebuilt import ToolNode
        except ImportError as err:
            raise ImportError(
                "ToolTrustToolNode requires langgraph; "
                "install with `pip install agent-tooltrust[langgraph]`"
            ) from err

        class _GuardedToolNode(ToolNode):
            def _run_one(  # type: ignore[override]
                self_guard: Any,
                call: Any,
                input_type: Any = None,
                *,
                tool_runtime: Any = None,
                **kwargs: Any,
            ) -> Any:
                tool_call_request = call if hasattr(call, "get") else {}
                tool_name = tool_call_request.get("name", "")
                args = tool_call_request.get("args", {}) or {}

                ctx = CallContext(
                    tool_name=tool_name,
                    action="call",
                    environment=self._environment,
                    data_class=self._data_class,
                    agent_id=self._agent_id,
                    arguments=args,
                )
                decision = self.intercept(ctx)

                if decision.decision in ("deny", "escalate"):
                    from langchain_core.messages import ToolMessage

                    return ToolMessage(
                        content=(f"[ToolTrust] {decision.decision}: {decision.explanation}"),
                        tool_call_id=tool_call_request.get("id", ""),
                    )

                return super()._run_one(
                    cast(Any, call), input_type, tool_runtime=tool_runtime, **kwargs
                )

        node = _GuardedToolNode(self._tools)
        return cast(dict[str, Any], node.invoke(state))
