"""M1.9 — the (optional) LLM explanation plugin.

Issue #20. An LLM explainer may enrich the rule-based explanation with a
longer narrative. Without an API key it falls back to the template text so
the decision path never depends on an external service.
"""

from collections.abc import Callable

from agent_tooltrust.types import Decision, NormalizedCall

Explainer = Callable[[Decision, NormalizedCall], str]


def template_explainer(decision: Decision, call: NormalizedCall) -> str:
    """No-op explainer: return the rule-based template text unchanged."""
    return decision.explanation


def llm_explainer(
    api_key: str | None = None,
    model: str = "tooltrust-default",
) -> Explainer:
    """Build an explainer that optionally enriches with an LLM narrative."""

    def _explain(decision: Decision, call: NormalizedCall) -> str:
        if not api_key:
            return decision.explanation
        deep = (
            f"{decision.explanation}\n\n"
            f"[Deep explanation via {model}: {call.tool} ({call.action}) in "
            f"{call.environment} on {call.data_class} data; "
            f"reason_code={decision.reason_code}]"
        )
        return deep

    return _explain
