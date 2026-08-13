"""Tests for M8.6 — ``tooltrust baseline check`` (#69).

The baseline command evaluates the Essential tier checklist and exits 0 only
when every item passes. These tests cover the happy path (all pass in the repo
checked out from source) and argparse plumbing for the subcommands.
"""

import pytest

from agent_tooltrust.cli import main
from agent_tooltrust.cli.baseline import (
    _audit_modules_present,
    _default_policy_denies_destructive,
    _fail_closed_enforced,
    _normalize_resists_confusables,
    _owasp_mapping_published,
    _strict_gates_configured,
)


class TestBaselineChecks:
    def test_fail_closed_handler_exists(self):
        ok, _ = _fail_closed_enforced()
        assert ok

    def test_default_policy_denies_destructive_prod(self):
        ok, detail = _default_policy_denies_destructive()
        assert ok, detail

    def test_confusable_normalization_resists(self):
        ok, detail = _normalize_resists_confusables()
        assert ok, detail

    def test_audit_modules_present(self):
        ok, detail = _audit_modules_present()
        assert ok, detail

    def test_strict_gates_configured(self):
        ok, detail = _strict_gates_configured()
        assert ok, detail

    def test_owasp_mapping_published(self):
        ok, detail = _owasp_mapping_published()
        assert ok, detail


class TestBaselineCli:
    def test_baseline_check_essential_passes(self):
        assert main(["baseline", "check", "essential"]) == 0

    def test_baseline_unknown_tier_raises(self):
        with pytest.raises(SystemExit) as exc:
            main(["baseline", "check", "nope"])
        assert exc.value.code == 2

    def test_baseline_requires_subcommand(self):
        assert main(["baseline"]) == 2
