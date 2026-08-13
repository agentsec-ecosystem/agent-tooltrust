"""Audit subsystem — model, sink interface, and logger facade.

Appends every decision (allow and deny alike) to a pluggable sink. The
default JSONL sink is dependency-free; SQLite and Postgres add local and
operational query surfaces. Sink failures are logged to stderr and never
block or change a decision.
"""

from agent_tooltrust.audit.logger import AuditLogger, build_sink, sink_from_config
from agent_tooltrust.audit.models import AuditEntry
from agent_tooltrust.audit.sink import AuditSink

__all__ = ["AuditEntry", "AuditLogger", "AuditSink", "build_sink", "sink_from_config"]
