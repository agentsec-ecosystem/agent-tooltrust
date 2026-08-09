"""Tests for M1.6 — the fail-closed decorator.

Issue #17. Any exception in the pipeline maps to a deny decision with the
correct machine-readable reason_code. Failures must never turn into allows.
"""

import pytest

from agent_tooltrust.engine.fail_closed import deny, fail_closed
from agent_tooltrust.errors import (
    DENY_EVALUATION_TIMEOUT,
    DENY_MALFORMED_INPUT,
    DENY_OPA_BACKEND_DOWN,
    DENY_POLICY_PARSE_ERROR,
    DENY_UNKNOWN_TOOL,
    EvaluationTimeoutError,
    MalformedInputError,
    OpaUnavailableError,
    PolicyParseError,
    UnknownToolError,
)


class TestDeny:
    def test_deny_builds_a_deny_decision(self):
        decision = deny(DENY_UNKNOWN_TOOL, "Tool not in taxonomy")
        assert decision.decision == "deny"
        assert decision.criticality == "critical"
        assert decision.reason_code == DENY_UNKNOWN_TOOL
        assert decision.explanation == "Tool not in taxonomy"
        assert decision.factors == []
        assert decision.escalation_id is None
        assert decision.dry_run is False

    def test_deny_accepts_policy_version(self):
        decision = deny(DENY_UNKNOWN_TOOL, "x", policy_version="2.1.0")
        assert decision.policy_version == "2.1.0"


class TestFailClosed:
    def test_passthrough_on_success(self):
        @fail_closed
        def ok(fn):
            return "result"

        assert ok(lambda: None) == "result"

    def test_unknown_tool_maps_to_deny_unknown_tool(self):
        @fail_closed
        def boom():
            raise UnknownToolError("nope")

        decision = boom()
        assert decision.decision == "deny"
        assert decision.reason_code == DENY_UNKNOWN_TOOL

    def test_malformed_input_maps_to_deny_malformed_input(self):
        @fail_closed
        def boom():
            raise MalformedInputError("blank")

        assert boom().reason_code == DENY_MALFORMED_INPUT

    def test_policy_parse_error_maps_to_deny(self):
        @fail_closed
        def boom():
            raise PolicyParseError("bad yaml")

        assert boom().reason_code == DENY_POLICY_PARSE_ERROR

    def test_opa_error_maps_to_deny(self):
        @fail_closed
        def boom():
            raise OpaUnavailableError("down")

        assert boom().reason_code == DENY_OPA_BACKEND_DOWN

    def test_timeout_maps_to_deny(self):
        @fail_closed
        def boom():
            raise EvaluationTimeoutError("slow")

        assert boom().reason_code == DENY_EVALUATION_TIMEOUT

    def test_unexpected_error_is_not_swallowed(self):
        @fail_closed
        def boom():
            raise ValueError("unexpected")

        with pytest.raises(ValueError):
            boom()
