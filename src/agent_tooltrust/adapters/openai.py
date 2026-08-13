"""OpenAI Agents SDK adapter — ``tooltrust_guardrail`` for native guardrails.

Wraps an OpenAI Agents SDK tool with a ``@tool_input_guardrail`` that evaluates
every call through the ToolTrust engine. A deny decision returns
``ToolGuardrailFunctionOutput.deny()``, which the SDK surfaces as a native
guardrail trip.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agent_tooltrust.adapters.base import BaseAdapter, CallContext
from agent_tooltrust.types import Decision


class OpenAIAdapter(BaseAdapter):
    """Guard OpenAI Agents SDK tools with ToolTrust evaluation.

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

    def guardrail(
        self,
        *,
        tool_name: str = "",
        action: str = "",
        environment: str = "production",
        data_class: str = "internal",
        agent_id: str = "",
    ) -> Callable[..., Any]:
        """Return a ``@tool_input_guardrail`` compatible function.

        The OpenAI Agents SDK calls the guardrail with a single
        ``ToolInputGuardrailData`` argument. Tool identity and context come
        from the decorator parameters, not the SDK context object.

        Args:
            tool_name: Tool identity for the engine.
            action: Action being performed.
            environment: Deployment environment.
            data_class: Data sensitivity label.
            agent_id: Agent identity.

        Returns:
            A callable suitable for ``@tool_input_guardrail``.
        """

        def guardrail_fn(data: Any, /) -> Any:
            try:
                from agents import ToolGuardrailFunctionOutput
            except ImportError:
                raise ImportError(
                    "openai-agents required; install `agent-tooltrust[openai-agents]`"
                ) from None

            ctx = CallContext(
                tool_name=tool_name or getattr(data.context, "tool_name", ""),
                action=action or "call",
                environment=environment,
                data_class=data_class,
                agent_id=agent_id,
                arguments=None,
            )
            decision = self.intercept(ctx)

            if decision.decision in ("deny", "escalate"):
                return ToolGuardrailFunctionOutput.reject_content(
                    message=f"[ToolTrust] {decision.decision}: {decision.explanation}"
                )
            return ToolGuardrailFunctionOutput.allow()

        return guardrail_fn
