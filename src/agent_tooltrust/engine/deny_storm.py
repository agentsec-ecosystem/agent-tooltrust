"""M4 Task 1 (#143) — deny-storm / policy-probe detection.

A session that is being probed shows a tell-tale shape in its decision stream:
dense denies, long runs of consecutive denies, escalation flooding, and a tool
set that keeps growing (the probe tries tool after tool). This analyzer turns
that stream into a per-session signal and, when a threshold is crossed, emits
an action the caller can enforce:

- ``pause`` — mild: many escalations in the window; give the agent a moment.
- ``throttle`` — strong: the deny rate or a consecutive-deny run crossed the
  bar; the session should be rate-limited.
- ``lock`` — severest: high deny rate **and** a broad tool set; the session
  looks like a probe, not a replan, and should be locked out.

The analyzer is deliberately *dumb and countable*: no probabilities, no
heuristics — just running totals over the last ``window_size`` decisions.
That keeps it deterministic, replayable from the audit log, and cheap enough
to run inside the engine after every decision.

Why a legit replan burst does **not** false-positive: replanning retries the
*same* tool with different arguments, so its deny rate is brief and its tool
set stays narrow (``tool_entropy`` near 0). A lock requires a high deny rate
*and* broad entropy, and a throttle requires the deny bar to be crossed over
at least ``min_decisions`` observations — a 2-3 retry replan cannot reach it
with the shipped defaults.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from math import log2

from agent_tooltrust.types import Decision, NormalizedCall

#: Severity ladder, weakest → strongest. The analyzer reports the strongest
#: signal that tripped; enforcement is left to the caller (server/engine).
PAUSE = "pause"
THROTTLE = "throttle"
LOCK = "lock"

_ACTIONS = (PAUSE, THROTTLE, LOCK)
_DECISION_DENY = "deny"


@dataclass(frozen=True)
class DenyStormConfig:
    """Thresholds for deny-storm detection per session.

    Attributes:
        window_size: How many recent decisions to evaluate signals over.
        min_decisions: Minimum observations before any action may be emitted
            (prevents a cold-start blip from tripping an alert).
        deny_rate_threshold: Fraction of the window that must be denies to
            throttle (in ``[0, 1]``).
        max_consecutive_denies: Consecutive deny run that triggers throttle.
        escalation_threshold: Escalations within the window that trigger a
            pause (probe of the human-approval path).
        entropy_threshold: Tool-set Shannon entropy (bits) that, combined
            with a high deny rate, triggers a lock.
        max_sessions: Cap on distinct tracked sessions; the least-recently
            observed session is evicted first so a long-running engine cannot
            grow this analyzer without bound.
    """

    window_size: int = 20
    min_decisions: int = 6
    deny_rate_threshold: float = 0.6
    max_consecutive_denies: int = 6
    escalation_threshold: int = 4
    entropy_threshold: float = 2.0
    max_sessions: int = 10_000

    def __post_init__(self) -> None:
        if self.window_size < 1:
            raise ValueError("window_size must be >= 1")
        if self.min_decisions < 1:
            raise ValueError("min_decisions must be >= 1")
        if not 0.0 <= self.deny_rate_threshold <= 1.0:
            raise ValueError("deny_rate_threshold must be in [0, 1]")
        if self.max_consecutive_denies < 1:
            raise ValueError("max_consecutive_denies must be >= 1")
        if self.escalation_threshold < 1:
            raise ValueError("escalation_threshold must be >= 1")
        if self.entropy_threshold < 0.0:
            raise ValueError("entropy_threshold must be >= 0")
        if self.max_sessions < 1:
            raise ValueError("max_sessions must be >= 1")


@dataclass(frozen=True)
class StormStatus:
    """The computed signal set for one session, plus the enforced action.

    Attributes:
        session_key: The session (or agent, when no session id is present).
        observed: How many decisions the analyzer has seen for this session.
        deny_rate: Fraction of the window that are denies.
        consecutive_denies: Length of the current trailing deny run.
        escalation_count: Escalations within the window.
        tool_entropy: Shannon entropy (bits) of the window's tool set.
        action: ``pause``/``throttle``/``lock`` when a threshold tripped,
            else ``None``.
        reason: Human text describing which signal tripped (empty when clear).
    """

    session_key: str
    observed: int
    deny_rate: float
    consecutive_denies: int
    escalation_count: int
    tool_entropy: float
    action: str | None = None
    reason: str = ""

    def to_dict(self) -> dict[str, object]:
        """JSON-friendly representation for dashboards and the audit trail."""
        return {
            "session": self.session_key,
            "observed": self.observed,
            "deny_rate": self.deny_rate,
            "consecutive_denies": self.consecutive_denies,
            "escalation_count": self.escalation_count,
            "tool_entropy": self.tool_entropy,
            "action": self.action,
            "reason": self.reason,
        }


class DenyStormAnalyzer:
    """Session-level deny-storm detector fed one decision at a time.

    Threads a sliding window of the last ``window_size`` decisions per session
    (a session with no id is keyed by agent id, so a session-less caller is
    still protected). Call :meth:`observe` after every decision; call
    :meth:`status` for the current signal + action.

    Args:
        config: Thresholds; defaults to the shipped ``DenyStormConfig``.
    """

    def __init__(self, config: DenyStormConfig | None = None) -> None:
        self._config = config or DenyStormConfig()
        self._windows: dict[str, deque[tuple[str, str]]] = {}

    @property
    def config(self) -> DenyStormConfig:
        """The thresholds in force for every session."""
        return self._config

    def observe(self, decision: Decision, call: NormalizedCall) -> None:
        """Record one decision into its session's window.

        The session key is the call's ``session_id`` when present, else the
        ``agent_id`` (a session-less caller is still tracked per agent). Both
        ``observe`` and :meth:`status` use the same keys, so a status for a
        session id returned by the engine always reflects its observations.

        Args:
            decision: The finished decision (allow/audit/escalate/deny/...).
            call: The call that produced it; its session/agent id keys state.
        """
        key = call.session_id or call.agent_id
        if key not in self._windows:
            # Bound memory on long-running engines: drop the least-recently
            # created session once the configured cap is reached, so an
            # attacker spraying many session ids cannot grow this dict forever.
            if len(self._windows) >= self._config.max_sessions:
                oldest = next(iter(self._windows))
                self._windows.pop(oldest, None)
        window = self._windows.setdefault(key, deque(maxlen=self._config.window_size))
        window.append((decision.decision, call.tool))

    def status(self, session_key: str | None) -> StormStatus:
        """Return the current signal set + action for a session key.

        A ``None`` key is a *fresh* bucket ("<unknown>") — it never matches an
        observed session, because :meth:`observe` always keys on a concrete
        session or agent id. It exists so direct callers can ask "what would a
        brand-new session look like" without constructing an id.

        Args:
            session_key: The session id (or agent id) to inspect.

        Returns:
            A :class:`StormStatus`; ``action`` is set only when a threshold
            has tripped on enough observations.
        """
        key = session_key or "<unknown>"
        window = self._windows.get(key)
        if not window:
            return StormStatus(
                session_key=key,
                observed=0,
                deny_rate=0.0,
                consecutive_denies=0,
                escalation_count=0,
                tool_entropy=0.0,
            )
        signals = self._signals(window)
        action, reason = self._decide(signals, len(window))
        return StormStatus(
            session_key=key,
            observed=len(window),
            deny_rate=signals[0],
            consecutive_denies=signals[1],
            escalation_count=signals[2],
            tool_entropy=signals[3],
            action=action,
            reason=reason,
        )

    def statuses(self) -> list[StormStatus]:
        """Return a status for every tracked session, sorted by key.

        Used by dashboards and operators to see which sessions are locked,
        throttled, or paused right now.
        """
        return [self.status(key) for key in sorted(self._windows)]

    @staticmethod
    def _signals(window: deque[tuple[str, str]]) -> tuple[float, int, int, float]:
        """Reduce a decision window into raw (deny_rate, consecutive, escalation, entropy).

        Args:
            window: The sliding window of ``(decision, tool)`` tuples.

        Returns:
            A ``(deny_rate, consecutive_denies, escalation_count, tool_entropy)``
            tuple.
        """
        total = len(window)
        denies = sum(1 for decision, _ in window if decision == _DECISION_DENY)
        consecutive = 0
        for decision, _ in reversed(window):
            if decision != _DECISION_DENY:
                break
            consecutive += 1
        escalations = sum(1 for decision, _ in window if decision == "escalate")
        tool_counts: dict[str, int] = {}
        for _, tool in window:
            tool_counts[tool] = tool_counts.get(tool, 0) + 1
        entropy = 0.0
        for count in tool_counts.values():
            p = count / total
            entropy -= p * log2(p)
        return denies / total, consecutive, escalations, entropy

    def _decide(
        self, signals: tuple[float, int, int, float], observed: int
    ) -> tuple[str | None, str]:
        """Map signals to an action using the config's thresholds.

        Lock requires breadth (entropy) *and* density (deny rate) — the probe
        shape; throttle tripped by density or a deny run; pause tripped by
        escalation flooding. Each reason names the signal that crossed.

        Args:
            signals: The ``(deny_rate, consecutive, escalation, entropy)`` tuple.
            observed: Total decisions observed in the window.

        Returns:
            ``(action, reason)``; action is ``None`` when the session is clear.
        """
        if observed < self._config.min_decisions:
            return None, ""
        deny_rate, consecutive, escalations, entropy = signals

        if (
            deny_rate >= self._config.deny_rate_threshold
            and entropy >= self._config.entropy_threshold
        ):
            return LOCK, (
                f"deny rate {deny_rate:.0%} over {observed} decisions with "
                f"tool-set entropy {entropy:.2f} bits"
            )
        if consecutive >= self._config.max_consecutive_denies:
            return THROTTLE, f"{consecutive} consecutive denies"
        if deny_rate >= self._config.deny_rate_threshold:
            return THROTTLE, (
                f"deny rate {deny_rate:.0%} over the last {observed} decisions"
            )
        if escalations >= self._config.escalation_threshold:
            return PAUSE, f"{escalations} escalations in the window"
        return None, ""

    def reset(self, session_key: str) -> None:
        """Forget all history for a session (e.g. after an operator unlock).

        Args:
            session_key: The session (or agent) id to clear.
        """
        self._windows.pop(session_key, None)

    def reset_all(self) -> None:
        """Forget every session's history."""
        self._windows.clear()


__all__ = [
    "LOCK",
    "PAUSE",
    "THROTTLE",
    "DenyStormAnalyzer",
    "DenyStormConfig",
    "StormStatus",
]
