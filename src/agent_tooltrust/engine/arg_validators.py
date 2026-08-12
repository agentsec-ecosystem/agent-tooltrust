"""Argument-level validators for tool call arguments.

Provides built-in validators (regex, range, path, URL) and a decorator
for registering custom validators.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

_ValidatorFn = Callable[..., bool]
_FactoryFn = Callable[..., Callable[..., bool]]


def arg_validator(name: str) -> Callable[[_ValidatorFn], _ValidatorFn]:
    """Decorator to register a named argument validator.

    Args:
        name: Unique name for this validator.

    Returns:
        A decorator that registers the function.
    """

    def decorator(fn: _ValidatorFn) -> _ValidatorFn:
        _custom_validators[name] = fn
        return fn

    return decorator


_custom_validators: dict[str, _ValidatorFn] = {}


def _regex_validator(pattern: str) -> Callable[[Any], bool]:
    """Validate that a value matches a regex pattern.

    Args:
        pattern: The regex pattern to match against.

    Returns:
        A function that checks if value matches the pattern.
    """

    def check(value: Any) -> bool:
        return bool(re.match(pattern, str(value)))

    return check


def _range_validator(min: float, max: float) -> Callable[[Any], bool]:
    """Validate that a numeric value falls within a range.

    Args:
        min: Minimum allowed value (inclusive).
        max: Maximum allowed value (inclusive).

    Returns:
        A function that checks if value is within range.
    """

    def check(value: Any) -> bool:
        try:
            v = float(value)
            return min <= v <= max
        except (TypeError, ValueError):
            return False

    return check


def _path_validator(root: str) -> Callable[[Any], bool]:
    """Validate that a path stays within a root directory.

    Args:
        root: The allowed root directory.

    Returns:
        A function that checks for path traversal.
    """

    def check(value: Any) -> bool:
        resolved = os.path.realpath(os.path.join(root, str(value)))
        root_resolved = os.path.realpath(root)
        return resolved.startswith(root_resolved + os.sep) or resolved == root_resolved

    return check


def _url_validator(scheme: str) -> Callable[[Any], bool]:
    """Validate that a URL uses an allowed scheme.

    Args:
        scheme: Allowed URL scheme (e.g., "https").

    Returns:
        A function that checks the URL scheme.
    """

    def check(value: Any) -> bool:
        try:
            parsed = urlparse(str(value))
            return parsed.scheme == scheme
        except Exception:
            return False

    return check


_BUILTINS: dict[str, Any] = {
    "regex": _regex_validator,
    "range": _range_validator,
    "path": _path_validator,
    "url": _url_validator,
}


def register_arg_validators() -> dict[str, Any]:
    """Return a combined registry of built-in and custom validators.

    Returns:
        A dict mapping validator names to factory functions.
    """
    registry: dict[str, Any] = {}
    registry.update(_BUILTINS)
    registry.update(_custom_validators)
    return registry
