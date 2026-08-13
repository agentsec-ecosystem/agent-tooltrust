"""llamaindex build_agent — real LlamaIndex agents guarded by ToolTrust."""

from __future__ import annotations

from typing import Any

from agent_tooltrust.engine.engine import Engine
from agent_tooltrust.policy.models import default_policy
from tests.field.agents import (
    API_KEY,
    ENDPOINT,
    MODEL,
    MissingFrameworkError,
    _tool_arg,
)


def build_agent(agent_id: str = "li-01", payload: dict[str, Any] | None = None) -> Any:
    """Build a real LlamaIndex agent for the given roster agent.

    Tools are built with ``FunctionTool`` and guarded with
    :class:`~agent_tooltrust.adapters.llamaindex.LlamaIndexAdapter`.

    Args:
        agent_id: Roster agent id (li-01 .. li-08).
        payload: Optional overrides (engine, policy).

    Returns:
        A ``llama_index.core.AgentRunner`` (ReActAgent).
    """
    try:
        from llama_index.core.agent import ReActAgent
        from llama_index.core.tools import FunctionTool
        from llama_index.llms.openai import OpenAI
    except ImportError as exc:
        raise MissingFrameworkError(
            "llamaindex shim requires llama-index-core + llama-index-llms-openai"
        ) from exc

    from agent_tooltrust.adapters.llamaindex import LlamaIndexAdapter

    engine = (payload or {}).get("engine") or Engine(default_policy("balanced"))
    adapter = LlamaIndexAdapter(engine=engine)

    tools = [
        FunctionTool.from_defaults(
            adapter.wrap_tool(_tool_arg(name, name), agent_id=agent_id),
            name=name,
        )
        for name in _agent_tools(agent_id)
    ]

    llm = OpenAI(model=MODEL, api_key=API_KEY, api_base=ENDPOINT)

    agent = ReActAgent(tools=tools, llm=llm, verbose=False)
    agent._tool_names = _agent_tools(agent_id)  # type: ignore[attr-defined]
    return agent


def _agent_tools(agent_id: str) -> list[str]:
    return {
        "li-01": ["get_weather"],
        "li-02": ["add"],
        "li-03": ["get_weather", "get_current_time"],
        "li-04": ["add", "get_weather", "echo"],
        "li-05": ["query_logs"],
        "li-06": ["search_docs", "get_current_time"],
        "li-07": ["add", "echo"],
        "li-08": ["query_logs", "get_current_time"],
    }.get(agent_id, ["get_weather"])
