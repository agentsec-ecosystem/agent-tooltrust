"""OpenTelemetry tracing for the ToolTrust decision engine.

Wraps Engine.evaluate() with OTel spans recording tool, action,
environment, data_class, agent_id, decision, reason_code, and latency.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor

from agent_tooltrust.types import Decision

if TYPE_CHECKING:
    from agent_tooltrust.engine.engine import Engine

_TRACER_NAME = "agent_tooltrust"


def setup_tracing(
    service_name: str = "tooltrust",
    console_export: bool = True,
) -> None:
    """Configure the global OTel tracer provider.

    Args:
        service_name: Service name for the tracer.
        console_export: If True, export spans to stdout via ConsoleSpanExporter.
    """
    provider = TracerProvider()
    if console_export:
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)


def trace_evaluate(
    engine: Engine,
    tracer_provider: TracerProvider | None = None,
) -> Any:
    """Return a traced version of engine.evaluate().

    Each call produces an OTel span with attributes for tool, action,
    environment, data_class, agent_id, decision, reason_code, and latency.

    Args:
        engine: An Engine instance.
        tracer_provider: Optional TracerProvider. Uses global if None.

    Returns:
        A wrapped evaluate function that produces OTel spans.
    """
    if tracer_provider is not None:
        tracer = trace.get_tracer(_TRACER_NAME, tracer_provider=tracer_provider)
    else:
        tracer = trace.get_tracer(_TRACER_NAME)

    def wrapped(
        tool_name: str,
        action: str,
        environment: str,
        data_class: str,
        agent_id: str,
        **kwargs: Any,
    ) -> Decision:
        start = time.monotonic()
        with tracer.start_as_current_span("Engine.evaluate") as span:
            span.set_attribute("tooltrust.tool_name", tool_name)
            span.set_attribute("tooltrust.action", action)
            span.set_attribute("tooltrust.environment", environment)
            span.set_attribute("tooltrust.data_class", data_class)
            span.set_attribute("tooltrust.agent_id", agent_id)
            decision = engine.evaluate(
                tool_name=tool_name,
                action=action,
                environment=environment,
                data_class=data_class,
                agent_id=agent_id,
                **kwargs,
            )
            elapsed = time.monotonic() - start
            span.set_attribute("tooltrust.decision", decision.decision)
            span.set_attribute("tooltrust.reason_code", decision.reason_code)
            span.set_attribute("tooltrust.latency_ms", elapsed * 1000)
            return decision

    return wrapped
