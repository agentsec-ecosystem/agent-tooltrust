"""Analytics HTTP endpoint for the ToolTrust MCP server (M7.5).

Aggregates the whole audit log into a compact compliance snapshot: total
decisions, decision and tool breakdowns, deny rate, and the most-denied
tools. Deterministic — keys and iteration order are sorted so the payload is
stable across calls.
"""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse


def register_analytics_routes(mcp: Any, core: Any) -> None:
    """Register the /api/analytics aggregation endpoint.

    Args:
        mcp: A FastMCP server instance.
        core: A :class:`ServerCore` instance.
    """
    _register_analytics(mcp, core)


def _register_analytics(mcp: Any, core: Any) -> None:
    @mcp.custom_route("/api/analytics", methods=["GET"])  # type: ignore[untyped-decorator]
    async def analytics(request: Request) -> JSONResponse:
        entries = core.audit_logger.query(None)
        return JSONResponse(_aggregate(entries))


def _aggregate(entries: list[Any]) -> dict[str, Any]:
    """Compute the analytics payload from a list of audit entries.

    Args:
        entries: Audit entries; ``AuditEntry``-like objects exposing
            ``decision``, ``tool``, and ``session_id``.

    Returns:
        A deterministic analytics dict sized to the recorded decisions.
    """
    total = len(entries)
    deny_count = 0
    by_decision: dict[str, int] = {}
    by_tool: dict[str, int] = {}
    deny_by_tool: dict[str, int] = {}
    sessions: dict[str, int] = {}

    for entry in entries:
        by_decision[entry.decision] = by_decision.get(entry.decision, 0) + 1
        by_tool[entry.tool] = by_tool.get(entry.tool, 0) + 1
        if entry.decision == "deny":
            deny_count += 1
            deny_by_tool[entry.tool] = deny_by_tool.get(entry.tool, 0) + 1
        if entry.session_id is not None:
            sessions[entry.session_id] = sessions.get(entry.session_id, 0) + 1

    deny_rate = deny_count / total if total else 0.0
    top_denied_tools = sorted(
        deny_by_tool.items(), key=lambda item: (-item[1], item[0])
    )[:5]

    return {
        "total_decisions": total,
        "by_decision": dict(sorted(by_decision.items())),
        "by_tool": dict(sorted(by_tool.items())),
        "deny_rate": deny_rate,
        "top_denied_tools": [tool for tool, _ in top_denied_tools],
        "sessions": dict(sorted(sessions.items())),
    }
