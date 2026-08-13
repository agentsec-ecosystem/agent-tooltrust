"""crewai build_agent — real CrewAI crew guarded by ToolTrust."""

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
    scenario_bound_tools,
)


def build_agent(agent_id: str = "crew-01", payload: dict[str, Any] | None = None) -> Any:
    """Build a real CrewAI single-agent crew for the given roster agent.

    The tool is wrapped with :class:`~agent_tooltrust.adapters.crewai.CrewAIAdapter`.

    Args:
        agent_id: Roster agent id (crew-01 .. crew-10).
        payload: Optional overrides (engine, policy).

    Returns:
        A ``crewai.Crew`` with one agent, one task, and the guarded tool.
    """
    try:
        from crewai import LLM as CrewLLM
        from crewai import Agent, Crew, Task
    except ImportError as exc:
        raise MissingFrameworkError(
            "crewai shim requires crewai; install with `pip install crewai`"
        ) from exc

    from agent_tooltrust.adapters.crewai import CrewAIAdapter

    engine = (payload or {}).get("engine") or Engine(default_policy("balanced"))
    adapter = CrewAIAdapter(engine=engine)

    llm = CrewLLM(
        model=f"openai/{MODEL}",
        base_url=ENDPOINT,
        api_key=API_KEY,
    )

    from crewai.tools import tool as crew_tool

    names = _agent_tools(agent_id)

    @crew_tool("get_weather")
    def get_weather(city: str) -> str:
        """Get the current weather for a city."""
        return f"The weather in {city} is sunny at 20C."

    tools = [
        adapter.wrap_tool(
            get_weather,
            tool_name=names[0],
            action=NATIVE_ACTION,
            environment=NATIVE_ENVIRONMENT,
            data_class=NATIVE_DATA_CLASS,
            agent_id=agent_id,
        )
    ]

    for spec in (payload or {}).get("scenarios", []):
        entry = scenario_bound_tools(engine, [spec], agent_id)[0]
        tools.append(crew_tool(entry["name"])(entry["fn"]))

    agent = Agent(
        role="Helpful Assistant",
        goal="Answer accurately, using the requested tool.",
        backstory="A simple assistant with tools.",
        llm=llm,
        tools=tools,
        verbose=False,
    )
    task = Task(
        description="{input}",
        expected_output="A direct answer.",
        agent=agent,
    )
    return Crew(agents=[agent], tasks=[task], verbose=False)


def _agent_tools(agent_id: str) -> list[str]:
    return {
        "crew-01": ["get_weather"],
        "crew-02": ["add"],
        "crew-03": ["get_weather", "search_docs"],
        "crew-04": ["get_weather", "get_current_time"],
        "crew-05": ["query_logs"],
        "crew-06": ["add", "echo"],
        "crew-07": ["http_get", "run_query"],
        "crew-08": ["get_weather", "add", "echo"],
        "crew-09": ["echo"],
        "crew-10": ["search_docs", "send_slack"],
    }.get(agent_id, ["get_weather"])
