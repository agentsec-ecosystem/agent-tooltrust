"""M4 Task 3 (#144) — external verification sink (dev.to 473185670, Edu).

An agent that *reports* a completed outcome cannot be trusted on its own
word — the report is a self-report. This sink verifies outcomes against
agent-unwritable external systems: API counters, VCS state, billing
snapshots. The verification hook is **read-only** by contract, so the agent
cannot forge the ground truth it is compared against.

The flow is:

1. The agent claims it completed work: a :class:`VerificationClaim` naming a
   ``kind`` (the external system) and the observed values it asserts.
2. The sink looks up the registered read-only hook for that kind.
3. The hook fetches ground truth (a snapshot). The claim's asserted values
   are diffed against that snapshot.
4. The sink produces a :class:`VerificationResult`: ``verified`` (asserted
   values match), ``contradicted`` (some asserted value disagrees with
   ground truth — a false "completed" report is caught here), or
   ``inconclusive`` (no hook registered, or the snapshot cannot answer).

Hooks are injected, so tests never touch real systems. A built-in
:class:`SnapshotHook` covers counters/billing state, and
:class:`GitHook` wraps read-only ``git`` commands for VCS verification.
"""

from __future__ import annotations

import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from agent_tooltrust.errors import (
    ALLOW_VERIFIED,
    DENY_VERIFICATION_CONTRADICTED,
)

#: Reason code for an outcome the sink could not verify.
UNKNOWN_VERIFICATION = "verification_inconclusive"

VERIFIED = "verified"
CONTRADICTED = "contradicted"
INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True)
class VerificationClaim:
    """An agent's self-reported outcome, to be checked against ground truth.

    Attributes:
        kind: The external system to consult (e.g. ``"api_counter"``,
            ``"vcs_commit"``, ``"billing"``).
        claimed: The values the agent asserts, keyed by observable name.
        agent_id: The identity making the claim.
        detail: Optional human context (e.g. the tool call that produced it).
    """

    kind: str
    claimed: dict[str, Any]
    agent_id: str
    detail: str = ""


@dataclass(frozen=True)
class VerificationResult:
    """The outcome of diffing a claim against external ground truth.

    Attributes:
        status: ``verified`` / ``contradicted`` / ``inconclusive``.
        reason_code: Machine-readable reason (allow/deny/inconclusive).
        explanation: Human text naming the asserted-vs-actual discrepancy.
        claimed: What the agent asserted.
        observed: What the external system reported (when available).
    """

    status: str
    reason_code: str
    explanation: str
    claimed: dict[str, Any]
    observed: dict[str, Any] = field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        """Whether the claim passed verification (verified only).

        A contradicted claim is a failed verification, not a pass — regardless
        of how compelling the report sounded.
        """
        return self.status == VERIFIED

    def to_dict(self) -> dict[str, Any]:
        """JSON-friendly representation for the audit trail."""
        return {
            "status": self.status,
            "reason_code": self.reason_code,
            "explanation": self.explanation,
            "claimed": self.claimed,
            "observed": self.observed,
        }


class VerificationHook(ABC):
    """Read-only ground-truth source for one kind of claim.

    Subclasses map a claim's asserted observables to what the external system
    currently reports. Implementations MUST NOT write to the external system
    — the hook is the agent-unwritable side of the verification.
    """

    kind: str = ""

    @abstractmethod
    def snapshot(self, claim: VerificationClaim) -> dict[str, Any]:
        """Return the current ground-truth values for the claim's observables.

        Args:
            claim: The claim being verified; selects which observables matter.

        Returns:
            A dict of observable -> value from the external system. May be
            empty when the system cannot answer.
        """


class SnapshotHook(VerificationHook):
    """An in-memory snapshot hook for counters, billing, etc.

    Wraps any agent-unwritable callable that returns current state (a store,
    an API, a fixture in tests). The returned dict is diffed field-by-field
    against the claim.

    Args:
        kind: The claim kind this hook answers.
        source: Callable returning the current state dict.
    """

    def __init__(self, kind: str, source: Any) -> None:
        self.kind = kind
        self._source = source

    def snapshot(self, claim: VerificationClaim) -> dict[str, Any]:
        """Delegate to the wrapped source (read-only by contract).

        A raising source is treated as "cannot answer" (empty snapshot) so the
        sink degrades to ``inconclusive`` instead of propagating an exception
        out of :meth:`VerificationSink.verify`.
        """
        try:
            return dict(self._source())
        except Exception:
            return {}


class GitHook(VerificationHook):
    """Read-only VCS verification via the system ``git`` binary.

    Answers claims of kind ``"vcs_commit"`` whose asserted observables are
    ``ref`` (a commit sha) and optionally ``branch``. A commit is *verified*
    when it exists in the repository and, when a branch is asserted, resolves
    to the same commit as the branch tip.

    Args:
        kind: The claim kind (default ``"vcs_commit"``).
        repo_path: The repository to query.
        git: git binary name for tests to inject.
    """

    def __init__(self, kind: str = "vcs_commit", repo_path: str = ".", git: str = "git") -> None:
        self.kind = kind
        self._repo_path = repo_path
        self._git = git

    def snapshot(self, claim: VerificationClaim) -> dict[str, Any]:
        """Resolve claimed refs/branches via read-only git commands."""
        return self._resolve(claim.claimed)

    def _resolve(self, claimed: dict[str, Any]) -> dict[str, Any]:
        ref = claimed.get("ref")
        branch = claimed.get("branch")
        observed: dict[str, Any] = {}
        if isinstance(ref, str) and ref:
            observed["ref"] = self._rev_parse(ref)
        if isinstance(branch, str) and branch:
            observed["branch"] = self._rev_parse(branch)
        return observed

    def _rev_parse(self, rev: str) -> str | None:
        """Return the resolved commit sha for *rev*, or ``None`` if unknown.

        Any failure — a missing repo, a missing git binary, an unreadable
        path — returns ``None`` so verification fails closed to
        ``contradicted``/``inconclusive`` rather than raising out of
        :meth:`verify`.
        """
        try:
            result = subprocess.run(  # noqa: S603 — argv[0] is the fixed git binary; rev is git's verified ref
                [self._git, "rev-parse", "--verify", f"{rev}^{{commit}}"],
                cwd=self._repo_path,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError:
            return None
        if result.returncode != 0:
            return None
        return result.stdout.strip() or None


class VerificationSink:
    """Diff agent self-reports against registered read-only hooks.

    The sink never writes to any external system; it only reads snapshots and
    compares them to claimed values. Multiple hooks may be registered (one per
    kind). A claim with no registered hook is ``inconclusive``.

    Args:
        hooks: Optional initial hooks.
    """

    def __init__(self, hooks: Any = None) -> None:
        self._hooks: dict[str, VerificationHook] = {}
        for hook in hooks or []:
            self.register(hook)

    def register(self, hook: VerificationHook) -> None:
        """Register a read-only hook for its claim kind.

        Args:
            hook: The hook to register. A later registration for the same
                kind replaces the earlier one.
        """
        self._hooks[hook.kind] = hook

    def unregister(self, kind: str) -> None:
        """Remove the hook for a kind (no-op when absent).

        Args:
            kind: The claim kind to forget.
        """
        self._hooks.pop(kind, None)

    def kinds(self) -> tuple[str, ...]:
        """The claim kinds this sink can currently verify, sorted."""
        return tuple(sorted(self._hooks))

    def verify(self, claim: VerificationClaim) -> VerificationResult:
        """Diff a claim against its hook's ground truth.

        Args:
            claim: The self-report to verify.

        Returns:
            A :class:`VerificationResult`. Every asserted observable that the
            hook can resolve must match for ``verified``; any mismatch is
            ``contradicted``; an unregistered kind or unknown observable is
            ``inconclusive``.
        """
        hook = self._hooks.get(claim.kind)
        if hook is None:
            return VerificationResult(
                status=INCONCLUSIVE,
                reason_code=UNKNOWN_VERIFICATION,
                explanation=f"no verification hook registered for {claim.kind!r}",
                claimed=dict(claim.claimed),
            )
        observed = hook.snapshot(claim)
        return _diff(claim, observed)


def _diff(claim: VerificationClaim, observed: dict[str, Any]) -> VerificationResult:
    """Diff a claim's asserted observables against an observed snapshot.

    Args:
        claim: The self-report being checked.
        observed: The external system's answer (may be partial or empty).

    Returns:
        ``verified`` when every asserted key resolves and matches; ``contradicted``
        when any asserted key resolves to a different value or a claimed ref
        does not exist; ``inconclusive`` when no asserted key can be answered.
    """
    checked = 0
    for key, asserted in claim.claimed.items():
        if key not in observed:
            continue
        checked += 1
        actual = observed[key]
        # ``None`` observed means the external system could not answer the
        # observable (e.g. a ref git cannot resolve). That contradicts any
        # concrete asserted value; an explicit claim of "none" matches None.
        if actual is None and asserted is not None:
            return VerificationResult(
                status=CONTRADICTED,
                reason_code=DENY_VERIFICATION_CONTRADICTED,
                explanation=f"claimed {key}={asserted!r} but it does not exist "
                            f"in {claim.kind!r}",
                claimed=dict(claim.claimed),
                observed=dict(observed),
            )
        if actual != asserted:
            return VerificationResult(
                status=CONTRADICTED,
                reason_code=DENY_VERIFICATION_CONTRADICTED,
                explanation=f"claimed {key}={asserted!r} but {claim.kind!r} "
                            f"reports {actual!r}",
                claimed=dict(claim.claimed),
                observed=dict(observed),
            )
    if checked == 0:
        return VerificationResult(
            status=INCONCLUSIVE,
            reason_code=UNKNOWN_VERIFICATION,
            explanation=f"{claim.kind!r} could not answer any asserted observable",
            claimed=dict(claim.claimed),
            observed=dict(observed),
        )
    return VerificationResult(
        status=VERIFIED,
        reason_code=ALLOW_VERIFIED,
        explanation=f"{checked} asserted observable(s) match {claim.kind!r}",
        claimed=dict(claim.claimed),
        observed=dict(observed),
    )


__all__ = [
    "CONTRADICTED",
    "INCONCLUSIVE",
    "UNKNOWN_VERIFICATION",
    "VERIFIED",
    "GitHook",
    "SnapshotHook",
    "VerificationClaim",
    "VerificationHook",
    "VerificationResult",
    "VerificationSink",
]
