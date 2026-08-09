"""CLI-specific error type (user-facing, no traceback)."""


class CliError(Exception):
    """A user-facing CLI failure (shown as ``tooltrust: error: ...``)."""
