"""Session replay HTTP endpoint for the ToolTrust MCP server (M7.5).

Replays the full decision chain for one session from the audit log so an
operator can see the exact sequence of calls and decisions that led to the
session's outcome. Read-only: reads directly from the shared AuditLogger.
"""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse


def register_sessions_routes(mcp: Any, core: Any) -> None:
    """Register the /api/sessions/<session_id> decision-chain endpoint.

    Args:
        mcp: A FastMCP server instance.
        core: A :class:`ServerCore` instance.
    """
    _register_replay(mcp, core)


def _register_replay(mcp: Any, core: Any) -> None:
    @mcp.custom_route("/api/sessions/{session_id}", methods=["GET"])  # type: ignore[untyped-decorator]
    async def session_replay(request: Request) -> JSONResponse:
        session_id = str(request.path_params.get("session_id", "")).strip()
        if not session_id:
            return JSONResponse({"error": "session_id required"}, status_code=400)
        entries = core.audit_logger.query(session_id)
        return JSONResponse(
            {
                "session_id": session_id,
                "calls": [e.to_dict() for e in entries],
                "call_count": len(entries),
            }
        )
