"""Field agent shims — real framework agents for the M7 field test.

Each ``build_agent(agent_id, payload=None)`` constructs a real, simple agent
for the given roster agent id using the framework's native API, wired to the
local LLM endpoint (OMLX default). Tools are guarded with the corresponding
tooltrust framework adapter so every call evaluates through the engine.

The roster (tests/field/agents.yaml) declares which agents exist and which
tools each exposes; this module is the runtime builder used by
``tooltrust field-test`` and the field integration tests.

Framework packages are optional: importing this module stays side-effect free,
and ``build_agent`` raises a clear ``ImportError`` naming the missing
framework and the ``pip install`` command to run.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

#: OpenAI-compatible endpoint for local model serving (OMLX default).
ENDPOINT = (
    os.environ.get("TOOLTRUST_FIELD_ENDPOINT")
    or os.environ.get("EVALFORGE_FIELD_ENDPOINT")
    or "http://127.0.0.1:8000/v1"
)
#: Model identifier served at the endpoint.
MODEL = (
    os.environ.get("TOOLTRUST_FIELD_MODEL")
    or os.environ.get("EVALFORGE_FIELD_MODEL")
    or "Qwen3.5-4B-4bit"
)


def _tool_arg(name: str, spec: str = "", docstring: str = "") -> Callable[..., Any]:
    """Build a simple real tool function for the given tool name.

    Args:
        name: Tool name.
        spec: Unused; reserved for future typed specs.
        docstring: Docstring for the tool.

    Returns:
        A plain Python function implementing the tool.
    """

    def _fn(city: str = "San Francisco") -> str:
        """Get current weather for a city."""
        return f"The weather in {city} is sunny at 20C."

    def _add(a: int, b: int) -> int:
        """Add two integers."""
        return a + b

    def _time() -> str:
        """Get the current date and time."""
        from datetime import datetime

        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _echo(text: str) -> str:
        """Echo the input text back."""
        return text

    def _search(query: str) -> list[str]:
        """Search for documents matching a query."""
        return [f"result for: {query}"]

    def _logs(limit: int = 10) -> list[str]:
        """Return recent log entries."""
        return [f"log line {i}" for i in range(limit)]

    fn = {
        "get_weather": _fn,
        "add": _add,
        "get_current_time": _time,
        "echo": _echo,
        "search_docs": _search,
        "query_logs": _logs,
    }.get(name, _echo)
    fn.__name__ = name
    if docstring:
        fn.__doc__ = docstring
    return fn


class MissingFrameworkError(ImportError):
    """Raised when the framework package is not installed."""
