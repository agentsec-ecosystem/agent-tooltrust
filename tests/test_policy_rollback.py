"""Tests for policy rollback and OPAL integration."""

from __future__ import annotations

import tempfile
from pathlib import Path

from agent_tooltrust.engine.engine import Engine
from agent_tooltrust.policy.models import default_policy


class TestEngineReloadPolicy:
    def test_reload_changes_policy(self) -> None:
        engine = Engine(default_policy("balanced"))
        assert engine.policy.posture == "balanced"
        new_policy = default_policy("strict")
        engine.reload_policy(new_policy)
        assert engine.policy.posture == "strict"

    def test_reload_updates_decision(self) -> None:
        engine = Engine(default_policy("balanced"))
        decision1 = engine.evaluate(
            "deploy_service", "write", "production", "restricted", "release-bot",
        )
        # Balanced: write in production escalates
        assert decision1.decision == "escalate"

        engine.reload_policy(default_policy("permissive"))
        assert engine.policy.posture == "permissive"
        assert engine.policy is not default_policy("balanced")


class TestPolicyRollbackCLI:
    def test_rollback_missing_path_returns_1(self) -> None:
        from agent_tooltrust.cli import main

        rc = main(["policy", "rollback", "--version", "v1"])
        assert rc == 1

    def test_rollback_with_versioned_policy(self) -> None:
        from agent_tooltrust.cli import main

        with tempfile.TemporaryDirectory() as td:
            v1_dir = Path(td) / "v1"
            v1_dir.mkdir()
            tools = v1_dir / "tools.yaml"
            tools.write_text("version: '1.0'\nposture: balanced\n")

            rc = main(["policy", "rollback", "--version", "v1", "--policy-path", td])
            assert rc == 0
