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
    ) -> Callable[[CallContext, Any], Any]:
        """Return a ``@tool_input_guardrail`` compatible function.

        Args:
            tool_name: Tool identity (defaults to ``ctx.tool_name``).
            action: Action (defaults to ``ctx.action``).
            environment: Deployment environment.
            data_class: Data sensitivity label.
            agent_id: Agent identity.

        Returns:
            A callable suitable for ``@tool_input_guardrail``.
        """

        def guardrail_fn(ctx_guard: CallContext, agent: Any) -> Any:
            resolved_tool = tool_name or ctx_guard.tool_name
            resolved_action = action or ctx_guard.action

            ctx = CallContext(
                tool_name=resolved_tool,
                action=resolved_action or "call",
                environment=environment or ctx_guard.environment,
                data_class=data_class or ctx_guard.data_class,
                agent_id=agent_id or ctx_guard.agent_id,
                arguments=ctx_guard.arguments,
            )
            decision = self.intercept(ctx)

            if decision.decision in ("deny", "escalate"):
                try:
                    from agents import ToolGuardrailFunctionOutput
                except ImportError:
                    raise ImportError(
                        "openai-agents required; install `agent-tooltrust[openai-agents]`"
                    ) from None
                return ToolGuardrailFunctionOutput.deny(
                    reason=f"[ToolTrust] {decision.decision}: {decision.explanation}"
                )
            return None

        return guardrail_fn
