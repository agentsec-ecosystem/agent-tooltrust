"""openai_agents build_agent — real OpenAI Agents SDK agents guarded by ToolTrust."""

from __future__ import annotations

from typing import Any

from agent_tooltrust.engine.engine import Engine
from agent_tooltrust.policy.models import default_policy
from tests.field.agents import MODEL, MissingFrameworkError, _tool_arg


def build_agent(agent_id: str = "oa-01", payload: dict[str, Any] | None = None) -> Any:
    """Build a real OpenAI Agents SDK agent for the given roster agent.

    Tools call through :class:`~agent_tooltrust.adapters.openai.OpenAIAdapter`.

    Args:
        agent_id: Roster agent id (oa-01 .. oa-08).
        payload: Optional overrides (engine, policy).

    Returns:
        An ``agents.Agent`` with guarded ``function_tool`` tools.
    """
    try:
        from agents import Agent, ModelSettings, set_tracing_disabled
    except ImportError as exc:
        raise MissingFrameworkError(
            "openai-agents shim requires openai-agents; install with `pip install openai-agents`"
        ) from exc

    set_tracing_disabled(disabled=True)

    from agent_tooltrust.adapters.openai import OpenAIAdapter

    engine = (payload or {}).get("engine") or Engine(default_policy("balanced"))
    adapter = OpenAIAdapter(engine=engine)

    guarded_tools = []
    for name in _agent_tools(agent_id):
        guarded_tools.append(_make_tool(name))

    agent = Agent(
        name=agent_id,
        instructions="You are a helpful assistant with a few tools.",
        tools=guarded_tools,
        model=MODEL,
        model_settings=ModelSettings(tool_choice="auto"),
    )
    agent._guard = adapter  # type: ignore[attr-defined]
    return agent


def _make_tool(name: str):
    from agents import function_tool

    fn = _tool_arg(name, name)
    return function_tool(name_override=name, strict_mode=False)(fn)


def _agent_tools(agent_id: str) -> list[str]:
    return {
        "oa-01": ["get_weather"],
        "oa-02": ["add"],
        "oa-03": ["get_weather", "get_current_time"],
        "oa-04": ["add", "get_weather", "echo"],
        "oa-05": ["query_logs"],
        "oa-06": ["search_docs", "get_current_time"],
        "oa-07": ["get_weather", "add"],
        "oa-08": ["echo", "query_logs"],
    }.get(agent_id, ["get_weather"])
