"""JSONL audit sink — the zero-dependency default.

Appends one ``AuditEntry`` per line to a log file (default
``~/.tooltrust/audit.jsonl``). Rotates to ``<path>.1`` when the file crosses
``max_bytes``. Writes are fire-and-forget: any ``OSError`` is reported to
stderr instead of raising, so a full disk never breaks a decision.

Each appended line carries the entry's ``chain_hash``/``prev_hash`` (see
``audit.tamper_proof``), so the on-disk log is a tamper-evident hash chain:
``audit verify`` and ``audit session --replay`` can recompute the links and
fail loudly if any line was modified, inserted, or deleted.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from agent_tooltrust.audit.models import AuditEntry
from agent_tooltrust.audit.sink import AuditSink
from agent_tooltrust.audit.tamper_proof import chain_entry


class JsonlSink(AuditSink):
    """Append entries as JSON lines to a local file."""

    def __init__(self, path: str | os.PathLike[str], max_bytes: int | None = None) -> None:
        self._path = Path(os.path.expanduser(os.fspath(path)))
        #: Rotation threshold; ``None`` disables rotation.
        self._max_bytes = max_bytes

    @property
    def path(self) -> Path:
        """The audit log file path."""
        return self._path

    def write(self, entry: AuditEntry) -> None:
        chained = chain_entry(entry, self._last_chain_hash())
        line = json.dumps(chained.to_dict(), sort_keys=True) + "\n"
        try:
            self._maybe_rotate()
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(line)
        except OSError as exc:
            print(f"tooltrust audit: jsonl write failed: {exc}", file=sys.stderr)

    def _last_chain_hash(self) -> str | None:
        """The ``chain_hash`` of the newest persisted line, if any."""
        if not self._path.exists():
            return None
        try:
            lines = [
                ln.strip()
                for ln in self._path.read_text(encoding="utf-8").splitlines()
                if ln.strip()
            ]
            if not lines:
                return None
            value = json.loads(lines[-1]).get("chain_hash")
            return value if isinstance(value, str) else None
        except (OSError, ValueError, KeyError):
            return None

    def _maybe_rotate(self) -> None:
        if self._max_bytes is None or not self._path.exists():
            return
        size = self._path.stat().st_size
        if size > self._max_bytes:
            self._path.rename(self._path.with_suffix(self._path.suffix + ".1"))

    def query(self, session_id: str | None = None) -> list[AuditEntry]:
        entries: list[AuditEntry] = []
        for line in _read_nonempty_lines(self._path):
            try:
                entry = AuditEntry.from_dict(json.loads(line))
            except (ValueError, KeyError, TypeError):
                continue
            if session_id is None or entry.session_id == session_id:
                entries.append(entry)
        return entries


def _read_nonempty_lines(path: Path) -> list[str]:
    """Read a JSONL file, skipping empty/corrupt lines. Missing file → []."""
    if not path.exists():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    return [line for line in text.splitlines() if line.strip()]
