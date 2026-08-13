"""Field agent registry — resolve any roster agent id to its build_agent.

``build_agent(agent_id, payload=None)`` loads the framework module for the
agent's prefix and delegates. Framework packages stay optional: building an
agent whose framework is not installed raises a clear ``ImportError``.
"""

from __future__ import annotations

from collections.abc import Callable
from importlib import import_module
from pathlib import Path
from typing import Any, cast

import yaml

#: agent_id prefix -> shim module name (no leading package).
PREFIX_MODULE: dict[str, str] = {
    "lg": "langgraph",
    "pai": "pydanticai",
    "crew": "crewai",
    "oa": "openai_agents",
    "ag": "autogen",
    "sm": "smolagents",
    "li": "llamaindex",
    "adk": "adk",
    "swe": "swebench",
    "mcp": "tooltrust_mcp",
}

_PACKAGE = "tests.field.agents"


def module_for(agent_id: str) -> str:
    """Return the shim module dotted path for an agent id.

    Args:
        agent_id: Roster agent id (e.g. ``lg-01``).

    Returns:
        The module path ``tests.field.agents.<framework>``.

    Raises:
        ValueError: When the prefix is unknown.
    """
    prefix = agent_id.split("-", 1)[0]
    try:
        module = PREFIX_MODULE[prefix]
    except KeyError as exc:
        raise ValueError(f"unknown agent prefix {prefix!r} for {agent_id!r}") from exc
    return f"{_PACKAGE}.{module}"


def builder_for(agent_id: str) -> Callable[[str, dict[str, Any] | None], Any]:
    """Return the ``build_agent`` callable for an agent id.

    Args:
        agent_id: Roster agent id.

    Returns:
        The framework module's ``build_agent`` function.

    Raises:
        ImportError: When the framework package is not installed.
    """
    module = import_module(module_for(agent_id))
    builder = module.build_agent
    return cast(Callable[[str, dict[str, Any] | None], Any], builder)


def build_agent(agent_id: str, payload: dict[str, Any] | None = None) -> Any:
    """Build a real framework agent for a roster agent id.

    Args:
        agent_id: Roster agent id.
        payload: Optional build overrides (engine, policy).

    Returns:
        The framework-native agent object.

    Raises:
        ImportError: When the framework package is not installed.
    """
    return builder_for(agent_id)(agent_id, payload)


def load_roster(path: str | Path = "tests/field/agents.yaml") -> list[dict[str, Any]]:
    """Load the agent roster YAML.

    Args:
        path: Path to the roster file.

    Returns:
        The list of agent dicts from the roster.
    """
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    items: Any = data["agents"] if isinstance(data, dict) else data
    return list(items)


def assert_sources_resolve(
    roster_path: str | Path = "tests/field/agents.yaml",
    vendor_root: str | Path = "tests/field/agents/vendor",
) -> list[str]:
    """Verify each roster agent's source exists in the vendor checkout.

    Args:
        roster_path: Path to the roster YAML.
        vendor_root: Root of the downloaded vendor checkouts.

    Returns:
        List of agent ids whose source could not be located.
    """
    unresolved: list[str] = []
    root = Path(vendor_root)
    for agent in load_roster(roster_path):
        source = agent["source"]
        if "tests/fixtures/" in source or source.startswith("agent_tooltrust"):
            continue
        path = root / source.split(" (")[0]
        if not path.exists():
            unresolved.append(agent["agent_id"])
    return unresolved
