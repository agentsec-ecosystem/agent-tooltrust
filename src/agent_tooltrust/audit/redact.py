"""Audit entry argument redaction — prevent PII/secrets in the audit log.

Redacts sensitive fields from tool-call arguments before they reach any sink.
Applied in ``AuditLogger.log()`` with a default deny-list plus optional
per-policy extras. Recurses into nested dicts and lists.
"""

from __future__ import annotations

from typing import Any

_REDACTED_PLACEHOLDER = "***REDACTED***"

DEFAULT_REDACT_KEYS: frozenset[str] = frozenset({
    k.lower()
    for k in (
        "token",
        "password",
        "apiKey",
        "api_key",
        "authorization",
        "secret",
        "key",
        "passwd",
        "credential",
        "access_token",
        "private_key",
        "api_secret",
        "client_secret",
        "auth_token",
        "bearer",
    )
})


def _redact_value(
    value: Any,
    keys: frozenset[str],
    *,
    _path: str = "",
) -> tuple[Any, bool]:
    """Recursively redact sensitive fields in a value.

    Args:
        value: The value to redact (dict, list, or scalar).
        keys: Set of lower-cased key names to treat as sensitive.
        _path: Dot-separated path for nested error reporting.

    Returns:
        A tuple of (redacted_value, was_redacted).
    """
    if isinstance(value, dict):
        redacted = False
        result: dict[str, Any] = {}
        for k, v in value.items():
            child_path = f"{_path}.{k}" if _path else k
            if isinstance(k, str) and k.lower() in keys:
                result[k] = _REDACTED_PLACEHOLDER
                redacted = True
            else:
                result[k], child_redacted = _redact_value(v, keys, _path=child_path)
                redacted = redacted or child_redacted
        return result, redacted

    if isinstance(value, list):
        redacted = False
        result_list: list[Any] = []
        for i, item in enumerate(value):
            redacted_item, item_redacted = _redact_value(
                item, keys, _path=f"{_path}[{i}]",
            )
            result_list.append(redacted_item)
            redacted = redacted or item_redacted
        return result_list, redacted

    return value, False


def redact_arguments(
    args: dict[str, Any] | None,
    extra_keys: set[str] | None = None,
) -> tuple[dict[str, Any] | None, bool]:
    """Redact sensitive fields from tool-call arguments.

    Args:
        args: The raw arguments dict (from ``NormalizedCall.arguments``).
        extra_keys: Additional redact keys from per-policy override.

    Returns:
        A tuple of (redacted_args, was_redacted). Returns the original
        ``args`` when no redaction was needed.
    """
    if args is None:
        return None, False

    keys = DEFAULT_REDACT_KEYS | frozenset(k.lower() for k in (extra_keys or ()))

    try:
        redacted, was_redacted = _redact_value(args, keys)
    except Exception:
        return {"_redact_error": "unredactable"}, True

    if not was_redacted:
        return args, False

    return redacted, True
