"""Tests for M1 #91 — policy pack format (tools.yaml + tests.yaml).

A pack is a directory (or tools.yaml path) carrying the policy document plus
an optional tests.yaml of golden decision fixtures. ``validate_pack`` checks
schema + reference integrity deterministically; ``run_pack_tests`` replays the
fixtures through the Engine without any LLM, so results are stable across runs.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_tooltrust.policy.pack import (
    PackError,
    run_pack_tests,
    validate_pack,
)

TOOLS_YAML = """\
version: "1.0.0"
posture: balanced
tools:
  - name: delete_instance
    hidden_for: [readonly]
  - name: read_secrets
    hidden_for: [readonly]
"""

GOOD_TESTS_YAML = """\
version: "1.0.0"
fixtures:
  - name: assign-role-denied-in-prod
    tool: assign_role
    action: grant
    environment: production
    data_class: restricted
    agent_id: release-bot
    expect: deny
  - name: query-logs-allowed-in-dev
    tool: query_logs
    action: read
    environment: development
    data_class: public
    agent_id: release-bot
    expect: allow
"""


def _write(tmp_path: Path, tools: str = TOOLS_YAML, tests: str | None = GOOD_TESTS_YAML) -> Path:
    d = tmp_path / "pack"
    d.mkdir()
    (d / "tools.yaml").write_text(tools)
    if tests is not None:
        (d / "tests.yaml").write_text(tests)
    return d


class TestValidatePack:
    def test_well_formed_pack_validates(self, tmp_path: Path) -> None:
        errors, policy = validate_pack(_write(tmp_path))
        assert errors == []
        assert policy.version == "1.0.0"

    def test_accepts_tools_yaml_path_instead_of_dir(self, tmp_path: Path) -> None:
        d = _write(tmp_path)
        errors, _ = validate_pack(d / "tools.yaml")
        assert errors == []

    def test_missing_tools_yaml(self, tmp_path: Path) -> None:
        d = tmp_path / "pack"
        d.mkdir()
        (d / "tests.yaml").write_text(GOOD_TESTS_YAML)
        errors, _ = validate_pack(d)
        assert any("tools.yaml" in e for e in errors)

    def test_malformed_tools_yaml_rejected(self, tmp_path: Path) -> None:
        tools = 'version: "1.0.0"\nrules:\n  - decision: saunter\n'
        errors, _ = validate_pack(_write(tmp_path, tools=tools))
        assert errors

    def test_unknown_key_in_tools_yaml_rejected(self, tmp_path: Path) -> None:
        errors, _ = validate_pack(_write(tmp_path, tools='version: "1.0.0"\nbogus: 1\n'))
        assert errors

    def test_duplicate_tool_names_rejected(self, tmp_path: Path) -> None:
        tools = TOOLS_YAML + "  - name: delete_instance\n"
        errors, _ = validate_pack(_write(tmp_path, tools=tools))
        assert any("duplicate" in e.lower() for e in errors)

    def test_missing_tests_yaml_is_not_an_error(self, tmp_path: Path) -> None:
        errors, _policy = validate_pack(_write(tmp_path, tests=None))
        assert errors == []

    def test_fixture_referencing_unknown_tool_is_error(self, tmp_path: Path) -> None:
        tests = GOOD_TESTS_YAML.replace("tool: query_logs", "tool: no_such_tool_xyz")
        errors, _ = validate_pack(_write(tmp_path, tests=tests))
        assert any("no_such_tool_xyz" in e for e in errors)

    def test_unknown_fixture_key_rejected(self, tmp_path: Path) -> None:
        tests = GOOD_TESTS_YAML.replace("expect: deny", "expect: deny\n    bogus: 1")
        errors, _ = validate_pack(_write(tmp_path, tests=tests))
        assert errors


class TestRunPackTests:
    def test_runs_fixtures_deterministically(self, tmp_path: Path) -> None:
        d = _write(tmp_path)
        first = run_pack_tests(d)
        second = run_pack_tests(d)
        assert [r.decision for r in first] == [r.decision for r in second]
        assert all(r.expected == r.decision for r in first)
        assert len(first) == 2

    def test_missing_tests_reports_zero_fixtures(self, tmp_path: Path) -> None:
        d = _write(tmp_path, tests=None)
        results = run_pack_tests(d)
        assert results == []

    def test_failing_fixture_reported(self, tmp_path: Path) -> None:
        tests = GOOD_TESTS_YAML.replace("expect: allow", "expect: deny")
        d = _write(tmp_path, tests=tests)
        results = run_pack_tests(d)
        assert any(r.expected != r.decision for r in results)

    def test_reference_to_unknown_tool_raises(self, tmp_path: Path) -> None:
        tests = GOOD_TESTS_YAML.replace("tool: query_logs", "tool: no_such_tool_xyz")
        d = _write(tmp_path, tests=tests)
        with pytest.raises(PackError):
            run_pack_tests(d)
