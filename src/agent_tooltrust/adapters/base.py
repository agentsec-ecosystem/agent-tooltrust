"""Base adapter types — common interface across all six framework adapters.

Every adapter wraps an :class:`~agent_tooltrust.engine.engine.Engine` and
provides an ``intercept`` entry point that translates a framework-specific tool
call descriptor into a :class:`~agent_tooltrust.types.Decision`. Deriving
adapters override ``intercept`` and may optionally override ``wrap_tool`` when
the framework exposes a decorator-based tool registration API.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from agent_tooltrust.types import Decision

if TYPE_CHECKING:
    from agent_tooltrust.engine.engine import Engine


@dataclass(frozen=True)
class CallContext:
    """The minimum information an adapter must extract from its framework.

    Every field maps to a parameter of ``Engine.evaluate`` so the adapter
    never needs to know how the engine normalizes, scores, or decides — it
    just assembles this struct and forwards it.
    """

    tool_name: str
    action: str
    environment: str
    data_class: str
    agent_id: str
    session_id: str | None = None
    arguments: dict[str, Any] | None = None
    context: dict[str, Any] | None = None


@dataclass  # not frozen — subclasses may set internal state
class BaseAdapter(ABC):
    """Abstract adapter that evaluates tool calls through a ToolTrust Engine.

    Args:
        engine: A configured :class:`~agent_tooltrust.engine.engine.Engine`.
    """

    engine: Engine = field()

    @abstractmethod
    def intercept(self, ctx: CallContext) -> Decision:
        """Evaluate a tool call and return the engine's Decision.

        Subclasses extract a ``CallContext`` from their framework's native
        call representation, pass it here, and act on the result:
        ``allow``/``audit`` → proceed; ``escalate`` → surface approval needed;
        ``deny`` → surface a framework-native error.

        Args:
            ctx: The normalised call context extracted from the framework.

        Returns:
            The engine's Decision for this call.
        """
        ...

    def wrap_tool(self, tool_fn: Callable[..., Any]) -> Callable[..., Any]:
        """Wrap a framework tool callable to intercept before execution.

        The default implementation raises ``NotImplementedError``; adapters
        whose frameworks expose a decorator-based tool API should override
        this method.

        Args:
            tool_fn: The framework-native tool callable to guard.

        Returns:
            A wrapped callable that evaluates through the engine before
            delegating to *tool_fn*.
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not support wrap_tool; use intercept() directly"
        )
