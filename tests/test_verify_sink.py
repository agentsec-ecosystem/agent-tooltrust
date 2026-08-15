"""Tests for M4 Task 3 (#144) — external verification sink.

Self-reports are diffed against agent-unwritable read-only hooks. A false
"completed" report must be caught; a report that matches external ground
truth (e.g. VCS state) is verified; an unverifiable report is inconclusive.
"""

from __future__ import annotations

from agent_tooltrust.engine.verify import (
    CONTRADICTED,
    INCONCLUSIVE,
    VERIFIED,
    GitHook,
    SnapshotHook,
    VerificationClaim,
    VerificationResult,
    VerificationSink,
)
from agent_tooltrust.errors import (
    ALLOW_VERIFIED,
    DENY_VERIFICATION_CONTRADICTED,
)


def _claim(kind: str = "api_counter", **claimed) -> VerificationClaim:
    return VerificationClaim(
        kind=kind,
        claimed=claimed or {"processed": 42},
        agent_id="report-bot",
        detail="test",
    )


class TestSnapshotHook:
    def test_matching_claim_verified(self):
        sink = VerificationSink([SnapshotHook("api_counter", lambda: {"processed": 42})])
        result = sink.verify(_claim(processed=42))
        assert result.status == VERIFIED
        assert result.reason_code == ALLOW_VERIFIED
        assert result.allowed is True

    def test_false_completed_report_caught(self):
        # The agent claims 42 processed; the counting system says 41.
        sink = VerificationSink([SnapshotHook("api_counter", lambda: {"processed": 41})])
        result = sink.verify(_claim(processed=42))
        assert result.status == CONTRADICTED
        assert result.reason_code == DENY_VERIFICATION_CONTRADICTED
        assert result.allowed is False
        assert "41" in result.explanation

    def test_claimed_value_absent_contradicts(self):
        sink = VerificationSink([SnapshotHook("billing", lambda: {"volume": 10})])
        result = sink.verify(_claim(kind="billing", events=100))
        # events is not in the snapshot; no asserted key is answerable.
        assert result.status == INCONCLUSIVE

    def test_raising_source_is_inconclusive(self):
        def boom() -> dict:
            raise RuntimeError("counting service down")

        sink = VerificationSink([SnapshotHook("api_counter", boom)])
        result = sink.verify(_claim(processed=42))
        assert result.status == INCONCLUSIVE

    def test_null_claimed_value_matches_null_observed(self):
        sink = VerificationSink([SnapshotHook("api_counter", lambda: {"processed": None})])
        result = sink.verify(_claim(kind="api_counter", processed=None))
        assert result.status == VERIFIED


class TestInconclusive:
    def test_no_hook_registered(self):
        sink = VerificationSink()
        result = sink.verify(_claim())
        assert result.status == INCONCLUSIVE

    def test_multi_observable_partial_answer(self):
        # Only one asserted key resolves; the other is unanswerable, but the
        # resolvable one matches -> verified for what it can answer.
        sink = VerificationSink([SnapshotHook("api_counter", lambda: {"processed": 5})])
        result = sink.verify(_claim(processed=5, rejected=1))
        assert result.status == VERIFIED
        assert "1 asserted observable" in result.explanation


class TestHookManagement:
    def test_register_replace(self):
        sink = VerificationSink([SnapshotHook("api_counter", lambda: {"processed": 1})])
        sink.register(SnapshotHook("api_counter", lambda: {"processed": 2}))
        assert sink.verify(_claim(processed=2)).status == VERIFIED

    def test_unregister(self):
        sink = VerificationSink([SnapshotHook("api_counter", lambda: {"processed": 1})])
        sink.unregister("api_counter")
        assert sink.verify(_claim(processed=1)).status == INCONCLUSIVE

    def test_kinds_sorted(self):
        sink = VerificationSink(
            [
                SnapshotHook("zzz", lambda: {}),
                SnapshotHook("aaa", lambda: {}),
                SnapshotHook("mmm", lambda: {}),
            ]
        )
        assert sink.kinds() == ("aaa", "mmm", "zzz")


class TestResult:
    def test_to_dict(self):
        sink = VerificationSink([SnapshotHook("api_counter", lambda: {"processed": 42})])
        payload = sink.verify(_claim(processed=42)).to_dict()
        assert payload["status"] == VERIFIED
        assert payload["claimed"] == {"processed": 42}
        assert payload["observed"] == {"processed": 42}

    def test_contradicted_not_allowed(self):
        result = VerificationResult(
            status=CONTRADICTED,
            reason_code=DENY_VERIFICATION_CONTRADICTED,
            explanation="mismatch",
            claimed={"processed": 42},
            observed={"processed": 41},
        )
        assert result.allowed is False


class TestGitHook:
    def test_verified_commit_matches_branch(self, tmp_path, monkeypatch):
        # Simulate git rev-parse: the claimed ref exists and matches the branch.
        def fake_run(cmd, cwd, capture_output, text, check):
            from types import SimpleNamespace

            rev = cmd[3].split("^{")[0]
            return SimpleNamespace(returncode=0, stdout=rev)

        monkeypatch.setattr("agent_tooltrust.engine.verify.subprocess.run", fake_run)
        sink = VerificationSink([GitHook(repo_path=str(tmp_path))])
        result = sink.verify(
            _claim(kind="vcs_commit", ref="abc123", branch="main")
        )
        assert result.status == VERIFIED

    def test_unknown_commit_contradicts(self, tmp_path, monkeypatch):
        def fake_run(cmd, cwd, capture_output, text, check):
            from types import SimpleNamespace

            rev = cmd[3].split("^{")[0]
            # The branch resolves to main-tip but the claimed ref does not.
            if rev == "abc123":
                return SimpleNamespace(returncode=1, stdout="")
            return SimpleNamespace(returncode=0, stdout="main-tip")

        monkeypatch.setattr("agent_tooltrust.engine.verify.subprocess.run", fake_run)
        sink = VerificationSink([GitHook(repo_path=str(tmp_path))])
        result = sink.verify(_claim(kind="vcs_commit", ref="abc123", branch="main"))
        assert result.status == CONTRADICTED
        assert "does not exist" in result.explanation

    def test_missing_repo_fails_closed_contradicts(self):
        # A nonexistent repo path must not raise; it resolves to None and the
        # diff reports a contradiction for the claimed ref.
        sink = VerificationSink([GitHook(repo_path="/no/such/repo")])
        result = sink.verify(_claim(kind="vcs_commit", ref="abc123"))
        assert result.status == CONTRADICTED

    def test_missing_git_binary_fails_closed(self, tmp_path):
        sink = VerificationSink(
            [GitHook(repo_path=str(tmp_path), git="definitely-not-git-xyz")]
        )
        result = sink.verify(_claim(kind="vcs_commit", ref="abc123"))
        assert result.status == CONTRADICTED


def test_verify_claim_repr():
    claim = _claim()
    assert claim.detail == "test"
    assert claim.agent_id == "report-bot"
