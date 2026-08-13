"""Tests for argument-level validators and custom risk dimensions."""

from __future__ import annotations

from agent_tooltrust.engine.arg_validators import (
    arg_validator,
    register_arg_validators,
)
from agent_tooltrust.engine.risk_dimensions import (
    clear_custom_dimensions,
    evaluate_risk_dimensions,
    register_risk_dimension,
)
from agent_tooltrust.types import NormalizedCall


class TestArgValidators:
    def test_regex_validator_passes(self) -> None:
        registry = register_arg_validators()
        result = registry["regex"](pattern=r"^[a-z_]+$")(value="hello_world")
        assert result is True

    def test_regex_validator_fails(self) -> None:
        registry = register_arg_validators()
        result = registry["regex"](pattern=r"^[a-z_]+$")(value="hello world!")
        assert result is False

    def test_range_validator_passes(self) -> None:
        registry = register_arg_validators()
        result = registry["range"](min=1, max=10)(value=5)
        assert result is True

    def test_range_validator_fails(self) -> None:
        registry = register_arg_validators()
        result = registry["range"](min=1, max=10)(value=20)
        assert result is False

    def test_path_validator_passes(self) -> None:
        registry = register_arg_validators()
        result = registry["path"](root="/tmp")(value="/tmp/output.txt")
        assert result is True

    def test_path_validator_path_traversal_fails(self) -> None:
        registry = register_arg_validators()
        result = registry["path"](root="/tmp")(value="/tmp/../../../etc/passwd")
        assert result is False

    def test_url_validator_passes(self) -> None:
        registry = register_arg_validators()
        result = registry["url"](scheme="https")(value="https://api.example.com")
        assert result is True

    def test_url_validator_wrong_scheme_fails(self) -> None:
        registry = register_arg_validators()
        result = registry["url"](scheme="https")(value="http://api.example.com")
        assert result is False

    def test_arg_validator_decorator(self) -> None:
        @arg_validator("is_positive")
        def is_positive(value: int) -> bool:
            return value > 0

        assert is_positive(value=5) is True
        assert is_positive(value=-1) is False

    def test_registry_contains_builtins(self) -> None:
        registry = register_arg_validators()
        assert "regex" in registry
        assert "range" in registry
        assert "path" in registry
        assert "url" in registry


class TestRiskDimensions:
    def setup_method(self) -> None:
        clear_custom_dimensions()

    def test_custom_dimension_registers(self) -> None:
        @register_risk_dimension("my_dim")
        def my_dim(call: NormalizedCall) -> float:
            return 0.5

        result = evaluate_risk_dimensions(
            NormalizedCall(
                tool="test", tool_category="test", action="read",
                action_class="read", environment="staging",
                data_class="public", agent_id="bot", agent_class="bot",
            )
        )
        assert "my_dim" in result
        assert result["my_dim"] == 0.5

    def test_multiple_dimensions_accumulate(self) -> None:
        @register_risk_dimension("dim_a")
        def dim_a(call: NormalizedCall) -> float:
            return 0.3

        @register_risk_dimension("dim_b")
        def dim_b(call: NormalizedCall) -> float:
            return 0.7

        result = evaluate_risk_dimensions(
            NormalizedCall(
                tool="test", tool_category="test", action="read",
                action_class="read", environment="staging",
                data_class="public", agent_id="bot", agent_class="bot",
            )
        )
        assert result["dim_a"] == 0.3
        assert result["dim_b"] == 0.7

    def test_no_dimensions_empty_result(self) -> None:
        result = evaluate_risk_dimensions(
            NormalizedCall(
                tool="test", tool_category="test", action="read",
                action_class="read", environment="staging",
                data_class="public", agent_id="bot", agent_class="bot",
            )
        )
        assert result == {}
