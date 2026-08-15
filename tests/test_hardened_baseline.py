"""Tests for the hardened baseline checks."""

from __future__ import annotations

from agent_tooltrust.cli.baseline import (
    TIERS,
    _argument_policy_present,
    _delegation_present,
    _deny_storm_present,
    _escalation_present,
    _output_inspector_present,
    _redaction_present,
    _session_analytics_present,
    _tamper_chain_verified,
)


class TestHardenedChecks:
    def test_all_hardened_checks_pass(self) -> None:
        checks = TIERS["hardened"]
        for chk in checks:
            ok, detail = chk.check()
            assert ok, f"{chk.id} ({chk.label}): {detail}"

    def test_output_inspector(self) -> None:
        ok, detail = _output_inspector_present()
        assert ok, detail

    def test_deny_storm(self) -> None:
        ok, detail = _deny_storm_present()
        assert ok, detail

    def test_argument_policy(self) -> None:
        ok, detail = _argument_policy_present()
        assert ok, detail

    def test_delegation(self) -> None:
        ok, detail = _delegation_present()
        assert ok, detail

    def test_escalation(self) -> None:
        ok, detail = _escalation_present()
        assert ok, detail

    def test_tamper_chain(self) -> None:
        ok, detail = _tamper_chain_verified()
        assert ok, detail

    def test_redaction(self) -> None:
        ok, detail = _redaction_present()
        assert ok, detail

    def test_session_analytics(self) -> None:
        ok, detail = _session_analytics_present()
        assert ok, detail
