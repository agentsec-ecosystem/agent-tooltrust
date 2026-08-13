"""pydanticai build_agent — real PydanticAI agent guarded by ToolTrust."""

from __future__ import annotations

from typing import Any

from agent_tooltrust.engine.engine import Engine
from agent_tooltrust.policy.models import default_policy
from tests.field.agents import (
    API_KEY,
    ENDPOINT,
    MODEL,
    NATIVE_ACTION,
    NATIVE_DATA_CLASS,
    NATIVE_ENVIRONMENT,
    MissingFrameworkError,
    _tool_arg,
    scenario_bound_tools,
)

_TOOLS = {
    "pai-01": ["get_weather"],
    "pai-02": ["add", "get_current_time"],
    "pai-03": ["get_weather", "search_docs"],
    "pai-04": ["echo", "get_current_time"],
    "pai-05": ["query_logs"],
    "pai-06": ["search_docs", "get_current_time"],
    "pai-07": ["add", "get_weather", "echo"],
    "pai-08": ["echo", "query_logs"],
    "pai-09": ["echo"],
    "pai-10": ["get_weather", "add"],
}


def _register_tool(agent: Any, fn: Any, name: str = "") -> None:
    """Register a guarded callable as an agent tool, capturing fn by value."""

    @agent.tool_plain(name=name or None)
    def _tool(**kwargs: Any) -> Any:
        return fn(**kwargs)


def build_agent(agent_id: str = "pai-01", payload: dict[str, Any] | None = None) -> Any:
    """Build a real PydanticAI agent with tooltrust-guarded tools."""
    try:
        from openai import AsyncOpenAI
        from pydantic_ai import Agent
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider
    except ImportError as exc:
        raise MissingFrameworkError(
            "pydanticai shim requires pydantic-ai + openai"
        ) from exc

    from agent_tooltrust.adapters.raw import RawAdapter

    engine = (payload or {}).get("engine") or Engine(default_policy("balanced"))
    adapter = RawAdapter(engine=engine)

    client = AsyncOpenAI(base_url=ENDPOINT, api_key=API_KEY)
    model = OpenAIChatModel(MODEL, provider=OpenAIProvider(openai_client=client))
    agent = Agent(model=model)

    for name in _TOOLS.get(agent_id, ["get_weather"]):
        fn = _tool_arg(name, name)
        guarded = adapter.guard(
            tool_name=name, action=NATIVE_ACTION,
            environment=NATIVE_ENVIRONMENT, data_class=NATIVE_DATA_CLASS,
            agent_id=agent_id,
        )(fn)
        _register_tool(agent, guarded, name=name)

    for spec in (payload or {}).get("scenarios", []):
        entry = scenario_bound_tools(engine, [spec], agent_id)[0]
        _register_tool(agent, entry["fn"], name=entry["name"])

    return agent
