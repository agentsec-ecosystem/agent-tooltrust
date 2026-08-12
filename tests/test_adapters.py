"""Integration tests for all six M4 framework adapters.

Each adapter is tested with real ToolTrust Engine calls (balanced policy)
against a low-risk call (allow) and a high-risk call (deny/escalate), verifying
the adapter-specific interception and error-surfacing contract.
"""

from agent_tooltrust.adapters.adk import AdkAdapter
from agent_tooltrust.adapters.autogen import AutoGenAdapter
from agent_tooltrust.adapters.base import CallContext
from agent_tooltrust.adapters.crewai import CrewAIAdapter
from agent_tooltrust.adapters.llamaindex import LlamaIndexAdapter
from agent_tooltrust.adapters.mcp import ToolTrustMCPWrapper
from agent_tooltrust.adapters.openai import OpenAIAdapter
from agent_tooltrust.adapters.pydantic import PydanticAIAdapter
from agent_tooltrust.adapters.raw import RawAdapter, ToolTrustDecisionError
from agent_tooltrust.adapters.smolagents import SmolagentsAdapter
from agent_tooltrust.engine.engine import Engine
from agent_tooltrust.policy.models import default_policy

LOW_RISK = CallContext(
    tool_name="query_logs",
    action="read",
    environment="staging",
    data_class="internal",
    agent_id="release-bot",
)

HIGH_RISK = CallContext(
    tool_name="deploy_service",
    action="deploy",
    environment="production",
    data_class="restricted",
    agent_id="dev-eng",
)

_LOW_GUARD = dict(
    tool_name="query_logs",
    action="read",
    environment="staging",
    data_class="internal",
    agent_id="release-bot",
)

_HIGH_GUARD = dict(
    tool_name="deploy_service",
    action="deploy",
    environment="production",
    data_class="restricted",
    agent_id="dev-eng",
)


def _engine():
    return Engine(default_policy("balanced"))


class TestBaseAdapter:
    def test_callcontext_fields(self):
        ctx = LOW_RISK
        assert ctx.tool_name == "query_logs"
        assert ctx.action == "read"
        assert ctx.environment == "staging"
        assert ctx.data_class == "internal"

    def test_callcontext_optional_defaults(self):
        ctx = CallContext(tool_name="t", action="a", environment="e", data_class="d", agent_id="g")
        assert ctx.session_id is None
        assert ctx.arguments is None
        assert ctx.context is None


class TestRawAdapter:
    def test_guard_allows_low_risk(self):
        adapter = RawAdapter(engine=_engine())
        called = False

        @adapter.guard(**_LOW_GUARD)
        def my_tool():
            nonlocal called
            called = True

        my_tool()
        assert called

    def test_guard_raises_on_high_risk(self):
        adapter = RawAdapter(engine=_engine())

        @adapter.guard(**_HIGH_GUARD)
        def my_tool():
            pass

        try:
            my_tool()
        except ToolTrustDecisionError as exc:
            assert exc.decision.decision in ("deny", "escalate")
            assert "[ToolTrust]" in str(exc)
        else:
            raise AssertionError("Expected ToolTrustDecisionError")

    def test_guard_defaults_to_fn_name(self):
        adapter = RawAdapter(engine=_engine())
        called = False

        @adapter.guard(**_LOW_GUARD)
        def query_logs():
            nonlocal called
            called = True

        query_logs()
        assert called

    def test_session_context_manager(self):
        adapter = RawAdapter(engine=_engine())
        called = False

        with adapter.session(agent_id="release-bot", session_id="sess_test"):

            @adapter.guard(
                tool_name="query_logs",
                action="read",
                environment="staging",
                data_class="internal",
            )
            def my_tool():
                nonlocal called
                called = True

            my_tool()
        assert called


class TestMCPWrapper:
    def test_wrap_call_allows_low_risk(self):
        class FakeMCPClient:
            class tools:
                @staticmethod
                def call(tool_name, arguments):
                    return {"result": f"called {tool_name}"}

        wrapper = ToolTrustMCPWrapper(FakeMCPClient(), _engine())
        result_fn = wrapper.wrap_call(
            "query_logs",
            {
                "__tooltrust_environment": "staging",
                "__tooltrust_data_class": "internal",
                "format": "json",
            },
        )
        result = result_fn()
        assert "result" in result
        assert "query_logs" in str(result)

    def test_wrap_call_denies_high_risk(self):
        class FakeMCPClient:
            class tools:
                @staticmethod
                def call(tool_name, arguments):
                    return {"result": "should not reach"}

        wrapper = ToolTrustMCPWrapper(FakeMCPClient(), _engine())
        result_fn = wrapper.wrap_call(
            "deploy_service",
            {
                "__tooltrust_environment": "production",
                "__tooltrust_data_class": "restricted",
            },
        )
        result = result_fn()
        assert result["isError"] is True
        assert "[ToolTrust]" in result["content"][0]["text"]

    def test_wrap_call_strips_meta_keys(self):
        calls = []

        class FakeMCPClient:
            class tools:
                @staticmethod
                def call(tool_name, arguments):
                    calls.append(arguments)
                    return {"ok": True}

        wrapper = ToolTrustMCPWrapper(FakeMCPClient(), _engine())
        wrapper.wrap_call(
            "query_logs",
            {
                "__tooltrust_environment": "staging",
                "__tooltrust_data_class": "internal",
                "limit": 10,
            },
        )()
        assert "__tooltrust_environment" not in (calls[0] or {})


class TestPydanticAIAdapter:
    def test_guard_allows_low_risk(self):
        adapter = PydanticAIAdapter(engine=_engine())
        called = False

        @adapter.guard(**_LOW_GUARD)
        def my_tool():
            nonlocal called
            called = True

        my_tool()
        assert called

    def test_guard_returns_error_on_deny(self):
        adapter = PydanticAIAdapter(engine=_engine())

        @adapter.guard(**_HIGH_GUARD, on_deny="error")
        def my_tool():
            return "should not run"

        result = my_tool()
        assert "[ToolTrust]" in result

    def test_guard_retry_not_installed_falls_back(self):
        adapter = PydanticAIAdapter(engine=_engine())

        @adapter.guard(**_HIGH_GUARD, on_deny="retry")
        def my_tool():
            pass

        try:
            my_tool()
        except RuntimeError as exc:
            assert "pydantic-ai" in str(exc)
        else:
            raise AssertionError("Expected RuntimeError about pydantic-ai")


class TestOpenAIAdapter:
    def test_guardrail_returns_none_on_allow(self):
        adapter = OpenAIAdapter(engine=_engine())
        guard_fn = adapter.guardrail()
        ctx = CallContext(
            tool_name="query_logs",
            action="read",
            environment="staging",
            data_class="internal",
            agent_id="release-bot",
        )
        result = guard_fn(ctx, None)
        assert result is None

    def test_guardrail_raises_when_agents_not_installed(self):
        adapter = OpenAIAdapter(engine=_engine())
        guard_fn = adapter.guardrail()
        ctx = HIGH_RISK
        try:
            guard_fn(ctx, None)
        except ImportError as exc:
            assert "openai-agents" in str(exc)
        else:
            raise AssertionError("Expected ImportError for openai-agents")


class TestCrewAIAdapter:
    def test_wrap_tool_allows_low_risk(self):
        adapter = CrewAIAdapter(engine=_engine())

        class FakeTool:
            name = "query_logs"

            def _run(self, **kwargs):
                return "success"

        tool = FakeTool()
        guarded = adapter.wrap_tool(tool, **_LOW_GUARD)
        assert guarded._run() == "success"

    def test_wrap_tool_returns_error_on_deny(self):
        adapter = CrewAIAdapter(engine=_engine())

        class FakeTool:
            name = "deploy_service"

            def _run(self, **kwargs):
                return "should not run"

        tool = FakeTool()
        guarded = adapter.wrap_tool(tool, **_HIGH_GUARD)
        result = guarded._run()
        assert "[ToolTrust]" in result


class TestBaseAdapterWrapTool:
    def test_default_wrap_tool_raises_not_implemented(self):
        adapter = RawAdapter(engine=_engine())

        def dummy():
            pass

        try:
            adapter.wrap_tool(dummy)
        except NotImplementedError:
            pass
        else:
            raise AssertionError("Expected NotImplementedError")


class TestMCPWrapperEdgeCases:
    def test_wrap_call_with_none_arguments(self):
        class FakeMCPClient:
            class tools:
                @staticmethod
                def call(tool_name, arguments):
                    return {"ok": True}

        wrapper = ToolTrustMCPWrapper(FakeMCPClient(), _engine())
        result_fn = wrapper.wrap_call("query_logs", None)
        result = result_fn()
        assert result["isError"] is True


class TestLangGraphAdapterNoop:
    def test_langgraph_import_error(self):
        from agent_tooltrust.adapters.langgraph import ToolTrustToolNode

        try:
            ToolTrustToolNode([], _engine())({})
        except ImportError as exc:
            assert "langgraph" in str(exc)
        else:
            raise AssertionError("Expected ImportError for langgraph")


class TestAutoGenAdapter:
    def test_wrap_tool_allows_low_risk_sync(self):
        adapter = AutoGenAdapter(engine=_engine())
        called = False

        def add(a, b):
            nonlocal called
            called = True
            return a + b

        guarded = adapter.wrap_tool(add, **_LOW_GUARD)
        assert guarded(1, 2) == 3
        assert called

    def test_wrap_tool_raises_on_high_risk_sync(self):
        adapter = AutoGenAdapter(engine=_engine())

        def deploy():
            return "should not run"

        guarded = adapter.wrap_tool(deploy, **_HIGH_GUARD)
        try:
            guarded()
        except ToolTrustDecisionError as exc:
            assert exc.decision.decision in ("deny", "escalate")
            assert "[ToolTrust]" in str(exc)
        else:
            raise AssertionError("Expected ToolTrustDecisionError")

    def test_wrap_tool_allows_async_low_risk(self):
        import asyncio

        adapter = AutoGenAdapter(engine=_engine())
        called = False

        async def add(a, b):
            nonlocal called
            called = True
            return a + b

        guarded = adapter.wrap_tool(add, **_LOW_GUARD)
        assert asyncio.run(guarded(1, 2)) == 3
        assert called

    def test_wrap_tool_raises_on_async_high_risk(self):
        import asyncio

        adapter = AutoGenAdapter(engine=_engine())

        async def deploy():
            return "should not run"

        guarded = adapter.wrap_tool(deploy, **_HIGH_GUARD)
        try:
            asyncio.run(guarded())
        except ToolTrustDecisionError as exc:
            assert exc.decision.decision in ("deny", "escalate")
        else:
            raise AssertionError("Expected ToolTrustDecisionError")

    def test_wrap_tool_defaults_to_fn_name(self):
        adapter = AutoGenAdapter(engine=_engine())
        called = False

        def query_logs():
            nonlocal called
            called = True
            return "ok"

        guarded = adapter.wrap_tool(
            query_logs,
            action="read",
            environment="staging",
            data_class="internal",
            agent_id="release-bot",
        )
        guarded()
        assert called


class TestSmolagentsAdapter:
    def test_wrap_tool_allows_low_risk(self):
        adapter = SmolagentsAdapter(engine=_engine())

        class FakeTool:
            name = "query_logs"

            def forward(self, **kwargs):
                return "success"

        tool = FakeTool()
        guarded = adapter.wrap_tool(tool, **_LOW_GUARD)
        assert guarded.forward() == "success"

    def test_wrap_tool_returns_error_on_deny(self):
        adapter = SmolagentsAdapter(engine=_engine())

        class FakeTool:
            name = "deploy_service"

            def forward(self, **kwargs):
                return "should not run"

        tool = FakeTool()
        guarded = adapter.wrap_tool(tool, **_HIGH_GUARD)
        result = guarded.forward()
        assert "[ToolTrust]" in result

    def test_wrap_tool_passes_kwargs(self):
        adapter = SmolagentsAdapter(engine=_engine())

        class FakeTool:
            name = "query_logs"

            def forward(self, **kwargs):
                return kwargs.get("fmt", "default")

        tool = FakeTool()
        guarded = adapter.wrap_tool(tool, **_LOW_GUARD)
        assert guarded.forward(fmt="json") == "json"


class TestLlamaIndexAdapter:
    def test_wrap_tool_allows_low_risk(self):
        adapter = LlamaIndexAdapter(engine=_engine())

        def query_logs(fmt="json"):
            return f"results-{fmt}"

        guarded = adapter.wrap_tool(query_logs, **_LOW_GUARD)
        assert guarded(fmt="json") == "results-json"

    def test_wrap_tool_raises_on_high_risk(self):
        adapter = LlamaIndexAdapter(engine=_engine())

        def deploy_service():
            return "should not run"

        guarded = adapter.wrap_tool(deploy_service, **_HIGH_GUARD)
        try:
            guarded()
        except ToolTrustDecisionError as exc:
            assert exc.decision.decision in ("deny", "escalate")
            assert "[ToolTrust]" in str(exc)
        else:
            raise AssertionError("Expected ToolTrustDecisionError")

    def test_wrap_tool_defaults_to_fn_name(self):
        adapter = LlamaIndexAdapter(engine=_engine())
        called = False

        def query_metrics():
            nonlocal called
            called = True
            return "ok"

        guarded = adapter.wrap_tool(
            query_metrics,
            action="read",
            environment="staging",
            data_class="public",
            agent_id="release-bot",
        )
        guarded()
        assert called


class TestAdkAdapter:
    def test_wrap_tool_allows_low_risk(self):
        adapter = AdkAdapter(engine=_engine())
        called = False

        def get_weather(city):
            nonlocal called
            called = True
            return f"sunny {city}"

        guarded = adapter.wrap_tool(get_weather, **_LOW_GUARD)
        assert guarded("SF") == "sunny SF"
        assert called

    def test_wrap_tool_raises_on_high_risk(self):
        adapter = AdkAdapter(engine=_engine())

        def deploy():
            return "should not run"

        guarded = adapter.wrap_tool(deploy, **_HIGH_GUARD)
        try:
            guarded()
        except ToolTrustDecisionError as exc:
            assert exc.decision.decision in ("deny", "escalate")
            assert "[ToolTrust]" in str(exc)
        else:
            raise AssertionError("Expected ToolTrustDecisionError")

    def test_wrap_tool_defaults_to_fn_name(self):
        adapter = AdkAdapter(engine=_engine())
        called = False

        def search_docs():
            nonlocal called
            called = True
            return "docs"

        guarded = adapter.wrap_tool(
            search_docs,
            action="read",
            environment="staging",
            data_class="internal",
            agent_id="release-bot",
        )
        guarded()
        assert called
