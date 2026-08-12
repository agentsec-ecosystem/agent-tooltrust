"""Custom risk dimension registry for the scoring engine.

Allows users to register custom risk scoring functions via a decorator,
which participate in the weighted scoring alongside the built-in dimensions.
"""

from __future__ import annotations

from collections.abc import Callable

from agent_tooltrust.types import NormalizedCall

_DimensionFn = Callable[[NormalizedCall], float]

_custom_dimensions: dict[str, _DimensionFn] = {}


def register_risk_dimension(name: str) -> Callable[[_DimensionFn], _DimensionFn]:
    """Decorator to register a custom risk dimension.

    Args:
        name: Unique dimension name (e.g., "code_review_required").

    Returns:
        A decorator that registers the dimension scoring function.

    Example:
        >>> @register_risk_dimension("code_review_required")
        ... def check_review(call: NormalizedCall) -> float:
        ...     return 0.8 if call.action == "push" else 0.0
    """

    def decorator(fn: _DimensionFn) -> _DimensionFn:
        _custom_dimensions[name] = fn
        return fn

    return decorator


def evaluate_risk_dimensions(call: NormalizedCall) -> dict[str, float]:
    """Evaluate all registered custom risk dimensions.

    Args:
        call: The normalized call to evaluate.

    Returns:
        A dict mapping dimension names to their scores (0.0-1.0).
    """
    return {name: fn(call) for name, fn in _custom_dimensions.items()}


def get_custom_dimensions() -> dict[str, _DimensionFn]:
    """Return all registered custom risk dimensions.

    Returns:
        A dict of dimension name to scoring function.
    """
    return dict(_custom_dimensions)


def clear_custom_dimensions() -> None:
    """Clear all registered custom risk dimensions (for testing)."""
    _custom_dimensions.clear()
