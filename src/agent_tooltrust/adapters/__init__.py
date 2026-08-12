"""Integration adapters — pluggable framework guards for ToolTrust.

Each adapter wraps an :class:`~agent_tooltrust.engine.engine.Engine` and
provides a framework-native interception point that evaluates every tool call
before side effects execute.
"""

from __future__ import annotations

from agent_tooltrust.adapters.base import BaseAdapter, CallContext

__all__ = ["BaseAdapter", "CallContext"]
