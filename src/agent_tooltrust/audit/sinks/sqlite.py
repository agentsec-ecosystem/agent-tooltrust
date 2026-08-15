"""SQLite audit sink — the local-query default.

Stores entries in ``~/.tooltrust/audit.db`` (or a caller-supplied path),
creating the ``audit_entries`` table on first write (schema matches
``docs/architecture/db-schema-sketch.md`` §Local). Serves ``query`` for the
``tooltrust audit`` CLI and session replay.

Each row records the entry's ``chain_hash``/``prev_hash`` (from
``audit.tamper_proof``) so the table stays a tamper-evident chain that
``audit verify``/``audit session --replay`` can check link-by-link.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

from agent_tooltrust.audit.models import AuditEntry
from agent_tooltrust.audit.sink import AuditSink
from agent_tooltrust.audit.tamper_proof import chain_entry

_COLUMNS = (
    "session_id",
    "call_id",
    "timestamp",
    "tool",
    "tool_category",
    "action",
    "action_class",
    "environment",
    "data_class",
    "agent_id",
    "agent_class",
    "decision",
    "criticality",
    "reason_code",
    "explanation",
    "factors",
    "policy_version",
    "dry_run",
    "escalation_id",
    "chain_hash",
    "prev_hash",
)

_CREATE = (
    "CREATE TABLE IF NOT EXISTS audit_entries ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, " + ", ".join(f"{col} TEXT" for col in _COLUMNS) + ")"
)

_COLUMNS_SQL = ", ".join(_COLUMNS)
_PLACEHOLDERS_SQL = ", ".join("?" for _ in _COLUMNS)
# Column names come from the fixed _COLUMNS constant above, never user input.
_INSERT_SQL = f"INSERT INTO audit_entries ({_COLUMNS_SQL}) VALUES ({_PLACEHOLDERS_SQL})"  # noqa: S608
_SELECT_ALL_SQL = f"SELECT {_COLUMNS_SQL} FROM audit_entries"  # noqa: S608
_SELECT_SESSION_SQL = f"SELECT {_COLUMNS_SQL} FROM audit_entries WHERE session_id = ?"  # noqa: S608
_SELECT_CHAIN_SQL = "SELECT chain_hash FROM audit_entries ORDER BY id DESC LIMIT 1"


def _default_path() -> Path:
    return Path("~").expanduser() / ".tooltrust" / "audit.db"


class SqliteSink(AuditSink):
    """Append entries to a local SQLite database."""

    def __init__(self, path: str | os.PathLike[str] | None = None) -> None:
        self._path = Path(os.path.expanduser(os.fspath(path or _default_path())))

    @property
    def path(self) -> Path:
        """The database file path."""
        return self._path

    def _connect(self) -> sqlite3.Connection:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._path)
        conn.execute(_CREATE)
        self._migrate(conn)
        return conn

    def _migrate(self, conn: sqlite3.Connection) -> None:
        """Add the tamper-chain columns to databases created before v0.2.

        Older audit_entries tables lack ``chain_hash``/``prev_hash``; those
        rows pre-date chaining and cannot be retro-verified, so they read
        back with ``NULL`` chain fields (an entry with no chain metadata is
        reported as unverifiable, not silently assumed valid).
        """
        existing = {
            row[1]
            for row in conn.execute("PRAGMA table_info(audit_entries)").fetchall()
        }
        for column in ("chain_hash", "prev_hash"):
            if column not in existing:
                conn.execute(f"ALTER TABLE audit_entries ADD COLUMN {column} TEXT")

    def write(self, entry: AuditEntry) -> None:
        try:
            with self._connect() as conn:
                prev_row = conn.execute(_SELECT_CHAIN_SQL).fetchone()
                prev_hash = prev_row[0] if prev_row else None
                chained = chain_entry(entry, prev_hash)
                params = [
                    chained.session_id,
                    chained.call_id,
                    chained.timestamp,
                    chained.tool,
                    chained.tool_category,
                    chained.action,
                    chained.action_class,
                    chained.environment,
                    chained.data_class,
                    chained.agent_id,
                    chained.agent_class,
                    chained.decision,
                    chained.criticality,
                    chained.reason_code,
                    chained.explanation,
                    json.dumps([f.to_dict() for f in chained.factors], sort_keys=True),
                    chained.policy_version,
                    int(chained.dry_run),
                    chained.escalation_id,
                    chained.chain_hash,
                    chained.prev_hash,
                ]
                conn.execute(_INSERT_SQL, params)
        except sqlite3.Error as exc:
            print(f"tooltrust audit: sqlite write failed: {exc}", file=sys.stderr)

    def query(self, session_id: str | None = None) -> list[AuditEntry]:
        try:
            conn = self._connect()
            if session_id is None:
                rows = conn.execute(_SELECT_ALL_SQL).fetchall()
            else:
                rows = conn.execute(_SELECT_SESSION_SQL, (session_id,)).fetchall()
            conn.close()
        except sqlite3.Error as exc:
            print(f"tooltrust audit: sqlite query failed: {exc}", file=sys.stderr)
            return []
        return [_row_to_entry(row) for row in rows]


def _row_to_entry(row: tuple[object, ...]) -> AuditEntry:
    values: dict[str, object] = {col: row[i] for i, col in enumerate(_COLUMNS)}
    factors = json.loads(str(values["factors"])) if values["factors"] else []
    values["factors"] = [
        {"dimension": f["dimension"], "value": f["value"], "contribution": f["contribution"]}
        for f in factors
    ]
    values["dry_run"] = str(values["dry_run"]).lower() in ("1", "true", "yes", "on")
    data = {k: v for k, v in values.items() if v is not None}
    return AuditEntry.from_dict(data)
