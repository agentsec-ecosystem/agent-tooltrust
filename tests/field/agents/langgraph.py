"""langgraph build_agent — real LangGraph agent guarded by ToolTrust."""

from __future__ import annotations

from typing import Any

from agent_tooltrust.engine.engine import Engine
from agent_tooltrust.policy.models import default_policy
from tests.field.agents import ENDPOINT, MODEL, MissingFrameworkError, _tool_arg

_TOOLS = {
    "lg-01": ["get_weather", "get_current_time"],
    "lg-02": ["add", "get_weather"],
    "lg-03": ["get_weather", "search_docs"],
    "lg-04": ["add", "get_weather", "get_current_time"],
    "lg-05": ["query_logs", "get_current_time"],
    "lg-06": ["add", "echo"],
}


def build_agent(agent_id: str = "lg-01", payload: dict[str, Any] | None = None) -> Any:
    """Build a real LangGraph agent with tooltrust-guarded tools."""
    try:
        from langchain_core.tools import tool as lg_tool
        from langchain_openai import ChatOpenAI
        try:
            from langchain.agents import create_agent as create_react_agent
        except ImportError:
            from langgraph.prebuilt import create_react_agent
    except ImportError as exc:
        raise MissingFrameworkError(
            "langgraph shim requires langgraph + langchain-openai + langchain-core"
        ) from exc

    from agent_tooltrust.adapters.raw import RawAdapter

    engine = (payload or {}).get("engine") or Engine(default_policy("balanced"))
    adapter = RawAdapter(engine=engine)

    tools = []
    for name in _TOOLS.get(agent_id, ["get_weather"]):
        fn = _tool_arg(name, name)
        guarded = adapter.guard(
            tool_name=name, action="call",
            environment="staging", data_class="internal",
            agent_id=agent_id,
        )(fn)
        tools.append(lg_tool(guarded))

    llm = ChatOpenAI(model=MODEL, base_url=ENDPOINT, api_key="omlx-test", temperature=0)
    return create_react_agent(llm, tools)
