"""Tests for M1.9 — the LLM explanation plugin.

Issue #20. An optional LLM explainer may enrich the decision explanation.
With no API key configured it must fall back to the template text and never
delay or fail the decision path.
"""

from agent_tooltrust.engine.decide import decide
from agent_tooltrust.engine.explain import explain
from agent_tooltrust.engine.llm_explain import llm_explainer, template_explainer
from agent_tooltrust.engine.score import score
from agent_tooltrust.policy.models import default_policy
from agent_tooltrust.types import NormalizedCall

POLICY = default_policy("balanced")


def _decision():
    call = NormalizedCall(
        tool="query_logs",
        tool_category="search",
        action="read",
        action_class="read",
        environment="staging",
        data_class="internal",
        agent_id="release-bot",
        agent_class="ci-bot",
    )
    verdict = decide(call, POLICY)
    return explain(verdict, score(call, POLICY), call, POLICY), call


class TestTemplateExplainer:
    def test_passthrough(self):
        decision, call = _decision()
        assert template_explainer(decision, call) == decision.explanation


class TestLlmExplainer:
    def test_falls_back_without_api_key(self):
        decision, call = _decision()
        explainer = llm_explainer()
        assert explainer(decision, call) == decision.explanation

    def test_enriches_with_api_key(self):
        decision, call = _decision()
        explainer = llm_explainer(api_key="k", model="fake-1")
        enriched = explainer(decision, call)
        assert enriched != decision.explanation
        assert decision.explanation in enriched
        assert "fake-1" in enriched

    def test_returns_a_string_for_deny(self):
        call = NormalizedCall(
            tool="drop_database",
            tool_category="db",
            action="delete",
            action_class="delete",
            environment="production",
            data_class="customer_pii",
            agent_id="untrusted-nobody",
            agent_class="general",
        )
        verdict = decide(call, POLICY)
        decision = explain(verdict, score(call, POLICY), call, POLICY)
        explainer = llm_explainer(api_key="k")
        assert isinstance(explainer(decision, call), str)
