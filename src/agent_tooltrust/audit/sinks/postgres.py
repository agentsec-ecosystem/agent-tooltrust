"""Postgres audit sink — operational backend (``asyncpg``).

Writes asynchronously through a shared connection pool. The public
``write``/``query`` API stays synchronous for the ``AuditSink`` contract by
driving the pool on a dedicated event-loop thread. On any connection or
statement failure the entry is queued to a local JSONL fallback buffer and a
warning goes to stderr — a Postgres outage never loses or blocks a decision.

``asyncpg`` is an optional dependency (``pip install agent-tooltrust[postgres]``);
this module imports it lazily so the default install stays dependency-free.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
import threading
from pathlib import Path
from typing import Any

from agent_tooltrust.audit.models import AuditEntry
from agent_tooltrust.audit.sink import AuditSink
from agent_tooltrust.audit.sinks.jsonl import JsonlSink

_DDL = (
    "CREATE TABLE IF NOT EXISTS audit_entries ("
    "id BIGSERIAL PRIMARY KEY, "
    "session_id TEXT NOT NULL, "
    "call_id TEXT, "
    "timestamp TIMESTAMPTZ NOT NULL, "
    "tool TEXT NOT NULL, "
    "tool_category TEXT, "
    "action TEXT NOT NULL, "
    "action_class TEXT, "
    "environment TEXT NOT NULL, "
    "data_class TEXT NOT NULL, "
    "agent_id TEXT NOT NULL, "
    "agent_class TEXT, "
    "decision TEXT NOT NULL, "
    "criticality TEXT NOT NULL, "
    "reason_code TEXT NOT NULL, "
    "explanation TEXT NOT NULL, "
    "factors JSONB, "
    "policy_version TEXT NOT NULL, "
    "dry_run BOOLEAN NOT NULL DEFAULT FALSE, "
    "escalation_id TEXT, "
    "approver TEXT"
    ")"
)

_INSERT = (
    "INSERT INTO audit_entries (session_id, call_id, timestamp, tool, tool_category, "
    "action, action_class, environment, data_class, agent_id, agent_class, "
    "decision, criticality, reason_code, explanation, factors, policy_version, "
    "dry_run, escalation_id, approver) "
    "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20)"
)

_SELECT = (
    "SELECT session_id, call_id, timestamp, tool, tool_category, action, action_class, "
    "environment, data_class, agent_id, agent_class, decision, criticality, "
    "reason_code, explanation, factors, policy_version, dry_run, escalation_id, "
    "approver FROM audit_entries"
)

_SELECT_SESSION = (
    "SELECT session_id, call_id, timestamp, tool, tool_category, action, action_class, "
    "environment, data_class, agent_id, agent_class, decision, criticality, "
    "reason_code, explanation, factors, policy_version, dry_run, escalation_id, "
    "approver FROM audit_entries WHERE session_id = $1"
)


def _require_asyncpg() -> None:
    """Import ``asyncpg`` or raise an informative ImportError."""
    if importlib.util.find_spec("asyncpg") is None:
        raise ImportError(
            "the postgres audit sink requires asyncpg; "
            "install with `pip install agent-tooltrust[postgres]`"
        )


class PostgresSink(AuditSink):
    """Append audit entries to a Postgres table via an asyncpg pool."""

    def __init__(
        self,
        url: str,
        fallback_path: str | os.PathLike[str] | None = None,
        pool_size: int = 5,
    ) -> None:
        self._url = url
        self._pool_size = pool_size
        self._fallback = JsonlSink(fallback_path or _default_fallback(), max_bytes=None)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._pool: Any | None = None

    def _ensure_runtime(self) -> None:
        """Spin up the background event loop and pool (idempotent)."""
        if self._pool is not None:
            return
        if self._loop is None or not self._loop.is_running():
            self._loop = asyncio.new_event_loop()
            threading.Thread(
                target=self._loop.run_forever, daemon=True, name="tooltrust-audit-pg"
            ).start()
        future = asyncio.run_coroutine_threadsafe(self._open_pool(), self._loop)
        try:
            self._pool = future.result(timeout=10)
        except Exception as exc:
            print(f"tooltrust audit: postgres pool failed: {exc}", file=sys.stderr)
            self._pool = None
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._loop = None

    async def _open_pool(self) -> Any:
        asyncpg = __import__("asyncpg")
        return await asyncpg.create_pool(self._url, min_size=1, max_size=self._pool_size)

    def _loop_for(self, loop: asyncio.AbstractEventLoop | None) -> asyncio.AbstractEventLoop:
        if loop is None:
            raise RuntimeError("postgres audit loop not running")
        return loop

    def write(self, entry: AuditEntry) -> None:
        _require_asyncpg()
        self._ensure_runtime()
        if self._pool is None:
            self._fallback.write(entry)
            return
        try:
            future = asyncio.run_coroutine_threadsafe(
                self._do_write(entry), self._loop_for(self._loop)
            )
            future.result(timeout=5)
        except Exception as exc:
            print(f"tooltrust audit: postgres write failed: {exc}", file=sys.stderr)
            self._fallback.write(entry)

    async def _do_write(self, entry: AuditEntry) -> None:
        if self._pool is None:
            return
        async with self._pool.acquire() as conn:
            await conn.execute(_DDL)
            await conn.execute(
                _INSERT,
                entry.session_id,
                entry.call_id,
                entry.timestamp,
                entry.tool,
                entry.tool_category,
                entry.action,
                entry.action_class,
                entry.environment,
                entry.data_class,
                entry.agent_id,
                entry.agent_class,
                entry.decision,
                entry.criticality,
                entry.reason_code,
                entry.explanation,
                json.dumps([f.to_dict() for f in entry.factors]),
                entry.policy_version,
                entry.dry_run,
                entry.escalation_id,
                entry.approver,
            )

    def query(self, session_id: str | None = None) -> list[AuditEntry]:
        _require_asyncpg()
        self._ensure_runtime()
        if self._pool is None:
            return self._fallback.query(session_id)
        try:
            future = asyncio.run_coroutine_threadsafe(
                self._do_query(session_id), self._loop_for(self._loop)
            )
            return list(future.result(timeout=5))
        except Exception as exc:
            print(f"tooltrust audit: postgres query failed: {exc}", file=sys.stderr)
            return self._fallback.query(session_id)

    async def _do_query(self, session_id: str | None) -> list[AuditEntry]:
        if self._pool is None:
            return []
        async with self._pool.acquire() as conn:
            if session_id is None:
                rows = await conn.fetch(_SELECT)
            else:
                rows = await conn.fetch(_SELECT_SESSION, session_id)
        return [_row_to_entry(row) for row in rows]


def _row_to_entry(row: Any) -> AuditEntry:
    data: dict[str, Any] = dict(row)
    factors = data.get("factors") or []
    if isinstance(factors, str):
        factors = json.loads(factors)
    data["factors"] = [
        {"dimension": f["dimension"], "value": f["value"], "contribution": f["contribution"]}
        for f in factors
    ]
    data["dry_run"] = bool(data.get("dry_run"))
    return AuditEntry.from_dict({k: v for k, v in data.items() if v is not None})


def _default_fallback() -> Path:
    return Path("~").expanduser() / ".tooltrust" / "audit-pg-fallback.jsonl"
