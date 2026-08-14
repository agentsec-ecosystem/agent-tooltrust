"""MCP server package for agent-tooltrust.

Exposes the core server components for programmatic use and provides the
``tooltrust serve`` CLI command.
"""

from agent_tooltrust.server.analytics_routes import register_analytics_routes
from agent_tooltrust.server.audit_routes import register_audit_routes
from agent_tooltrust.server.baselines_routes import register_baselines_routes
from agent_tooltrust.server.cli import add_parser as _serve_add_parser
from agent_tooltrust.server.dashboard import register_dashboard_route
from agent_tooltrust.server.escalation_routes import register_escalation_routes
from agent_tooltrust.server.mcp_tools import register_tools
from agent_tooltrust.server.seed import register_seed_route
from agent_tooltrust.server.server_core import ServerCore
from agent_tooltrust.server.session_store import SessionState, SessionStore
from agent_tooltrust.server.sessions_routes import register_sessions_routes

__all__ = [
    "ServerCore",
    "SessionState",
    "SessionStore",
    "_serve_add_parser",
    "register_analytics_routes",
    "register_audit_routes",
    "register_baselines_routes",
    "register_dashboard_route",
    "register_escalation_routes",
    "register_seed_route",
    "register_sessions_routes",
    "register_tools",
]
