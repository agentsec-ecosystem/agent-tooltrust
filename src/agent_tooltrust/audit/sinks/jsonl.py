"""JSONL audit sink — the zero-dependency default.

Appends one ``AuditEntry`` per line to a log file (default
``~/.tooltrust/audit.jsonl``). Rotates to ``<path>.1`` when the file crosses
``max_bytes``. Writes are fire-and-forget: any ``OSError`` is reported to
stderr instead of raising, so a full disk never breaks a decision.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from agent_tooltrust.audit.models import AuditEntry
from agent_tooltrust.audit.sink import AuditSink


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
        line = json.dumps(entry.to_dict(), sort_keys=True) + "\n"
        try:
            self._maybe_rotate()
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(line)
        except OSError as exc:
            print(f"tooltrust audit: jsonl write failed: {exc}", file=sys.stderr)

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
