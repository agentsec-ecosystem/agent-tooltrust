"""Escalation HTTP endpoints for the ToolTrust MCP server (M7.5 #150).

Human-in-the-loop approval surfaced over HTTP for the operator console:
list pending escalations and approve/deny them, backed by the
EscalationManager shared through the engine. Any decision (approve/deny) is
also reflected in the manager's persisted state so CLI and web stay in sync.

All endpoints return JSON. Approval to an unknown/already-resolved/expired
escalation yields a 409 — the engine is never bypassed.
"""

from __future__ import annotations

import json
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse


def register_escalation_routes(mcp: Any, core: Any) -> None:
    """Register /api/escalations, /api/escalations/<id>/approve, and deny.

    Args:
        mcp: A FastMCP server instance.
        core: A :class:`ServerCore` instance.
    """
    _register_pending(mcp, core)
    _register_approve(mcp, core)
    _register_deny(mcp, core)


def _register_pending(mcp: Any, core: Any) -> None:
    @mcp.custom_route("/api/escalations", methods=["GET"])  # type: ignore[untyped-decorator]
    async def escalation_list(request: Request) -> JSONResponse:
        show_all = request.query_params.get("all") == "true"
        status_filter = request.query_params.get("status")
        records = list(core.escalation_manager.records.values())
        if status_filter:
            records = [r for r in records if r.status.value == status_filter]
        elif not show_all:
            from agent_tooltrust.engine.escalation import EscalationStatus

            records = [r for r in records if r.status == EscalationStatus.PENDING]
        return JSONResponse([r.to_dict() for r in records])


def _register_approve(mcp: Any, core: Any) -> None:
    @mcp.custom_route("/api/escalations/{esc_id}/approve", methods=["POST"])  # type: ignore[untyped-decorator]
    async def escalation_approve(request: Request) -> JSONResponse:
        esc_id = str(request.path_params.get("esc_id", ""))
        body = await _json_body(request)
        approver = str(
            (body or {}).get("approver") or request.query_params.get("approver")
            or _default_user()
        )
        manager = core.escalation_manager
        try:
            record = manager.approve(esc_id, approver=approver)
        except ValueError as exc:
            return JSONResponse({"error": str(exc), "escalation_id": esc_id}, status_code=409)
        _persist(manager)
        return JSONResponse(record.to_dict())


def _register_deny(mcp: Any, core: Any) -> None:
    @mcp.custom_route("/api/escalations/{esc_id}/deny", methods=["POST"])  # type: ignore[untyped-decorator]
    async def escalation_deny(request: Request) -> JSONResponse:
        esc_id = str(request.path_params.get("esc_id", ""))
        body = await _json_body(request)
        approver = str(
            (body or {}).get("approver") or request.query_params.get("approver")
            or _default_user()
        )
        reason = str((body or {}).get("reason", ""))
        manager = core.escalation_manager
        try:
            record = manager.deny(esc_id, approver=approver, reason=reason)
        except ValueError as exc:
            return JSONResponse({"error": str(exc), "escalation_id": esc_id}, status_code=409)
        _persist(manager)
        return JSONResponse(record.to_dict())


def _default_user() -> str:
    """Fallback approver identity when none is supplied."""
    import getpass

    return getpass.getuser() or "unknown"


def _persist(manager: Any) -> None:
    """Persist the escalation store to its configured file (Docker volume).

    Non-fatal: when ``TOOLTRUST_ESCALATIONS_FILE`` is not set, approvals live
    only in memory (same as the in-process engine). When set, the decision
    survives container restarts via the mounted volume.
    """
    import os

    path = os.environ.get("TOOLTRUST_ESCALATIONS_FILE")
    if path:
        try:
            manager.save(path)
        except OSError:
            pass


async def _json_body(request: Request) -> dict[str, Any] | None:
    """Best-effort parse of the JSON request body; ``None`` when absent/invalid."""
    try:
        raw = await request.body()
    except Exception:
        return None
    if not raw:
        return None
    try:
        parsed = json.loads(raw.decode("utf-8", errors="replace"))
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None
