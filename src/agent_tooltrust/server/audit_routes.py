"""Audit HTTP endpoint for the ToolTrust MCP server.

Provides read-only /audit and /audit/health endpoints registered as custom
routes on the FastMCP server. Shares AuditLogger and SessionStore through
ServerCore.
"""

from __future__ import annotations

import time
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse


def register_audit_routes(mcp: Any, core: Any) -> float:
    """Register /audit and /audit/health custom routes on a FastMCP server.

    Args:
        mcp: A FastMCP server instance.
        core: A :class:`ServerCore` instance.

    Returns:
        The start time (monotonic seconds) used for uptime calculation.
    """
    start_time = time.time()

    @mcp.custom_route("/audit", methods=["GET"])  # type: ignore[untyped-decorator]
    async def audit_list(request: Request) -> JSONResponse:
        session_id = request.query_params.get("session")
        decision_filter = request.query_params.get("decision")
        entries = core.audit_logger.query(session_id)

        if decision_filter:
            entries = [e for e in entries if e.decision == decision_filter]

        result = [e.to_dict() for e in entries]
        return JSONResponse(result)

    @mcp.custom_route("/audit/health", methods=["GET"])  # type: ignore[untyped-decorator]
    async def audit_health(request: Request) -> JSONResponse:
        sessions = core.session_store.list_sessions()
        return JSONResponse({
            "status": "ok",
            "policy_version": getattr(core.engine, "policy_version", "unknown"),
            "uptime": time.time() - start_time,
            "sessions_active": len(sessions),
        })

    return start_time
