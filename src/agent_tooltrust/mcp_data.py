"""MCP-Data connector — per-data-source authorization on the ToolTrust pipeline.

Maps a data-source access request onto the normal engine by modelling each
source as a ``mcp_data.<source_id>`` tool in the ``db`` domain, with the
source's own id carried as ``data_class``. Operators register known sources
with :func:`register_data_source`; unregistered sources fail closed (deny).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from agent_tooltrust.taxonomy import register_tool

Operation = Literal["read", "write", "delete"]


@dataclass(frozen=True)
class DataAccessRequest:
    """A request to access a named data source with a given operation."""

    data_source_id: str
    operation: Operation
    agent_id: str
    environment: str
    session_id: str | None = None


def register_data_source(source_id: str, domain: str = "db") -> None:
    """Register a data source so ``mcp_data.<id>`` resolves through the engine.

    Args:
        source_id: The data-source identifier (also its policy ``data_class``).
        domain: Taxonomy domain to map the tool to (default ``db``).

    Raises:
        ValueError: If ``source_id`` is blank.
    """
    name = source_id.strip()
    if not name:
        raise ValueError("source_id must be a non-blank string")
    register_tool(f"mcp_data.{name}", domain)


def authorize_data_source(request: DataAccessRequest, core: Any) -> dict[str, Any]:
    """Authorize a data-source access through the shared decision core.

    Args:
        request: The data access to authorize.
        core: A :class:`ServerCore` instance.

    Returns:
        The Decision dict from ``ServerCore.evaluate``, including
        ``session_risk_score`` and ``call_id``.
    """
    source_id = request.data_source_id.strip()
    return core.evaluate(
        tool_name=f"mcp_data.{source_id}",
        action=request.operation,
        environment=request.environment,
        data_class=source_id,
        agent_id=request.agent_id,
        session_id=request.session_id,
    )