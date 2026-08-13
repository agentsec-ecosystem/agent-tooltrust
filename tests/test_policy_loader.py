"""Tests for M2.2 — the policy loader (#2, F-60).

Merge order (late wins): shipped posture preset (``default_policy``) → org
``tooltrust.yaml``. The loader must:
- build a full :class:`Policy` from a partial org file by overlaying it on the
  posture default (per-key dict merge, partial risk_weights, rules replaced
  when the org declares any),
- convert schema risk maps (criticality/sensitivity nests) to flat policy maps,
- raise :class:`PolicyParseError` — carrying ``DENY_POLICY_PARSE_ERROR`` —
  for missing files, YAML syntax errors, and schema violations, with the
  offending line/column surfaced in the message.
"""

from pathlib import Path

import pytest

from agent_tooltrust.errors import DENY_POLICY_PARSE_ERROR, PolicyParseError
from agent_tooltrust.policy.loader import _first_line_column, load_policy, load_policy_text
from agent_tooltrust.policy.models import Policy, default_policy


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "tooltrust.yaml"
    path.write_text(text)
    return path


class TestLoadsAndMerges:
    def test_bare_document_equals_balanced_default(self):
        policy = load_policy_text('version: "1.0.0"')
        assert policy == default_policy("balanced")
        assert policy.posture == "balanced"

    def test_org_posture_picks_preset(self):
        policy = load_policy_text('version: "1.0.0"\nposture: strict')
        assert policy == default_policy("strict")

    def test_environments_merge_late_wins(self):
        policy = load_policy_text(
            'version: "2.0.0"\nenvironments:\n  production: {criticality: 0.95}\n'
        )
        merged = default_policy("balanced").environments | {"production": 0.95}
        assert policy.version == "2.0.0"
        assert policy.environments == merged

    def test_data_classes_merge_late_wins(self):
        policy = load_policy_text('version: "2.0.0"\ndata_classes:\n  public: {sensitivity: 0.2}\n')
        merged = default_policy("balanced").data_classes | {"public": 0.2}
        assert policy.data_classes == merged

    def test_risk_weights_partial_merge(self):
        policy = load_policy_text('version: "2.0.0"\nrisk_weights:\n  action_class: 0.9\n')
        assert policy.risk_weights["action_class"] == 0.9
        for dim in ("tool_category", "environment", "data_sensitivity", "agent_class"):
            assert policy.risk_weights[dim] == 1.0

    def test_org_rules_replace_posture_defaults(self):
        policy = load_policy_text(
            'version: "2.0.0"\nrules:\n  - decision: deny\n    tool: curl\n    reason: "no"\n'
        )
        assert len(policy.rules) == 1
        assert policy.rules[0].tool == "curl"
        assert policy.rules[0].reason == "no"

    def test_no_rules_keeps_posture_defaults(self):
        policy = load_policy_text('version: "2.0.0"')
        assert policy.rules == default_policy("balanced").rules

    def test_reason_defaults_to_empty(self):
        policy = load_policy_text('version: "2.0.0"\nrules:\n  - decision: deny\n')
        assert policy.rules[0].reason == ""

    def test_agents_from_default_always_present(self):
        policy = load_policy_text('version: "2.0.0"')
        assert policy.agent_profile("release-bot") == default_policy("balanced").agent_profile(
            "release-bot"
        )


class TestRaisesPolicyParseError:
    def test_missing_file(self, tmp_path):
        with pytest.raises(PolicyParseError) as exc:
            load_policy(tmp_path / "nope.yaml")
        assert exc.value.reason_code == DENY_POLICY_PARSE_ERROR

    def test_directory_path_rejected(self, tmp_path):
        with pytest.raises(PolicyParseError):
            load_policy(tmp_path)

    def test_yaml_syntax_error_includes_line_and_column(self, tmp_path):
        path = write(tmp_path, "version: [1, 2\n  posture: balanced\n")
        with pytest.raises(PolicyParseError) as exc:
            load_policy(path)
        message = str(exc.value)
        assert "line" in message.lower() or "column" in message.lower()

    def test_schema_violation_includes_line(self, tmp_path):
        path = write(
            tmp_path, 'version: "1.0.0"\nenvironments:\n  production: {criticality: 2.5}\n'
        )
        with pytest.raises(PolicyParseError) as exc:
            load_policy(path)
        message = str(exc.value)
        assert "3" in message  # the production line
        assert "criticality" in message

    def test_schema_violation_in_rule_includes_line(self, tmp_path):
        path = write(
            tmp_path,
            'version: "1.0.0"\nrules:\n  - decision: saunter\n    tool: curl\n',
        )
        with pytest.raises(PolicyParseError) as exc:
            load_policy(path)
        assert "3" in str(exc.value)

    def test_non_mapping_document_wrapped_as_policy_error(self):
        with pytest.raises(PolicyParseError) as exc:
            load_policy_text("- a\n- b\n")
        assert exc.value.reason_code == DENY_POLICY_PARSE_ERROR

    def test_yaml_error_without_mark_still_wrapped(self, monkeypatch):
        import yaml

        import agent_tooltrust.policy.loader as loader_mod

        def boom(text: str) -> object:
            raise yaml.YAMLError("bad thing")

        monkeypatch.setattr("agent_tooltrust.policy.loader.parse_tooltrust_yaml", boom)
        with pytest.raises(PolicyParseError) as exc:
            loader_mod.load_policy_text('version: "1.0.0"')
        assert "bad thing" in str(exc.value)

    def test_unreadable_file_wrapped_as_policy_error(self, tmp_path, monkeypatch):
        from pathlib import Path

        import agent_tooltrust.policy.loader as loader_mod

        real = Path.read_text

        def boom(self, **kwargs):
            raise OSError("denied")

        monkeypatch.setattr(Path, "read_text", boom)
        try:
            with pytest.raises(PolicyParseError):
                loader_mod.load_policy(tmp_path / "x.yaml")
        finally:
            monkeypatch.setattr(Path, "read_text", real)


class TestLocationWalker:
    """White-box coverage of the YAML-node walker's defensive branches."""

    TEXT = 'version: "1.0.0"\nenvironments:\n  production: {criticality: 2.5}\n'

    def test_resolves_nested_flow_value(self):
        line, _ = _first_line_column(self.TEXT, ("environments", "production", "criticality"))
        assert line == 3

    def test_int_step_on_mapping_falls_back(self):
        assert _first_line_column(self.TEXT, ("environments", 0)) == (1, 1)

    def test_str_step_on_scalar_falls_back(self):
        assert _first_line_column(self.TEXT, ("version", "extra")) == (1, 1)

    def test_walk_continues_past_missing_node(self):
        assert _first_line_column(self.TEXT, ("environments", "missing", "nested")) == (1, 1)

    def test_int_step_out_of_range_falls_back(self):
        assert _first_line_column(self.TEXT, ("environments", "production", "criticality", 99)) == (
            1,
            1,
        )


def test_loads_from_real_file(tmp_path):
    path = write(tmp_path, 'version: "3.1.4"\nposture: permissive\n')
    policy = load_policy(path)
    assert isinstance(policy, Policy)
    default = default_policy("permissive")
    assert policy.posture == "permissive"
    assert policy.version == "3.1.4"
    assert policy.environments == default.environments
    assert policy.rules == default.rules
