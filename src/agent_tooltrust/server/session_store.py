"""In-memory, thread-safe session store for tracking cumulative risk and budgets.

SessionState tracks per-session risk accumulation, budgets, consent scopes,
and decision history. SessionStore provides thread-safe CRUD and enforcement
checks (budget exceeded, consent scope boundaries).
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SessionState:
    """Mutable state for one tool-using session.

    Args:
        session_id: Unique session identifier.
        risk_score: Cumulative risk across all calls in this session.
        tool_call_count: Number of tool calls made so far.
        token_budget: Optional ceiling on token usage (reserved for v0.2).
        call_budget: Optional ceiling on tool calls (count).
        consent_scopes: List of scopes the session is pre-approved for.
            Each scope is a dict with ``tool``, ``env``, ``data_class`` keys.
        decision_history: Rolling window of the last 50 decisions.
        created_at: Unix timestamp of session creation.
        last_updated: Unix timestamp of last state update.
    """

    session_id: str
    risk_score: float = 0.0
    tool_call_count: int = 0
    token_budget: int | None = None
    call_budget: int | None = None
    consent_scopes: list[dict[str, str]] = field(default_factory=list)
    decision_history: list[dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=time.monotonic)
    last_updated: float = field(default_factory=time.monotonic)
    rate_limit: float | None = None
    burst_limit: int | None = None
    _bucket: float = 0.0
    _last_bucket_fill: float = 0.0


class SessionStore:
    """Thread-safe in-memory store for per-session state.

    Args:
        history_limit: Maximum number of decision entries to keep per session.
    """

    def __init__(self, history_limit: int = 50) -> None:
        self._sessions: OrderedDict[str, SessionState] = OrderedDict()
        self._lock = threading.Lock()
        self._history_limit = history_limit

    def get_or_create(
        self,
        session_id: str,
        call_budget: int | None = None,
        token_budget: int | None = None,
        consent_scopes: list[dict[str, str]] | None = None,
    ) -> SessionState:
        """Return existing session or create a new one.

        Args:
            session_id: Unique session identifier.
            call_budget: Optional call count ceiling for new sessions.
            token_budget: Optional token budget ceiling for new sessions.
            consent_scopes: Optional consent scopes for new sessions.

        Returns:
            The existing or newly created SessionState.
        """
        with self._lock:
            if session_id in self._sessions:
                return self._sessions[session_id]
            state = SessionState(
                session_id=session_id,
                call_budget=call_budget,
                token_budget=token_budget,
                consent_scopes=list(consent_scopes or []),
            )
            self._sessions[session_id] = state
            return state

    def get(self, session_id: str) -> SessionState | None:
        """Return the session state or None if not found.

        Args:
            session_id: Unique session identifier.

        Returns:
            The SessionState or None.
        """
        with self._lock:
            return self._sessions.get(session_id)

    def update(
        self,
        session_id: str,
        risk_increment: float,
        call_id: str,
    ) -> SessionState:
        """Accumulate risk, increment call count, and record a decision.

        Args:
            session_id: Unique session identifier.
            risk_increment: Risk score to add to the cumulative total.
            call_id: The call_id of the audit entry for this decision.

        Returns:
            The updated SessionState.

        Raises:
            KeyError: If the session does not exist.
        """
        with self._lock:
            if session_id not in self._sessions:
                raise KeyError(session_id)
            state = self._sessions[session_id]
            state.risk_score += risk_increment
            state.tool_call_count += 1
            state.last_updated = time.monotonic()
            state.decision_history.append(
                {
                    "call_id": call_id,
                    "risk_increment": risk_increment,
                    "risk_score": state.risk_score,
                    "tool_call_count": state.tool_call_count,
                    "timestamp": time.monotonic(),
                }
            )
            if len(state.decision_history) > self._history_limit:
                state.decision_history = state.decision_history[-self._history_limit :]
            return state

    def exceeds_budget(self, session_id: str) -> tuple[bool, str | None]:
        """Check if the session has exceeded its budget.

        Args:
            session_id: Unique session identifier.

        Returns:
            A tuple of ``(exceeded: bool, reason: str | None)``. When exceeded,
            ``reason`` describes which budget was exceeded.
        """
        with self._lock:
            state = self._sessions.get(session_id)
            if state is None:
                return False, None
            if state.call_budget is not None and state.tool_call_count >= state.call_budget:
                return True, f"call budget exceeded ({state.tool_call_count}/{state.call_budget})"
            return False, None

    def within_consent(
        self,
        session_id: str,
        tool: str,
        env: str,
        data_class: str,
    ) -> bool:
        """Check if a tool call falls within the session's consent scopes.

        Args:
            session_id: Unique session identifier.
            tool: The tool name.
            env: The environment.
            data_class: The data classification.

        Returns:
            True if the call is within consent scopes or if no scopes are set.
        """
        with self._lock:
            state = self._sessions.get(session_id)
            if state is None:
                return True
            if not state.consent_scopes:
                return True
            for scope in state.consent_scopes:
                tool_match = scope["tool"] == "*" or scope["tool"] == tool
                env_match = scope["env"] == "*" or scope["env"] == env
                data_match = scope["data_class"] == "*" or scope["data_class"] == data_class
                if tool_match and env_match and data_match:
                    return True
            return False

    def list_sessions(self) -> list[str]:
        """Return all active session IDs.

        Returns:
            A list of session_id strings.
        """
        with self._lock:
            return list(self._sessions.keys())

    def patch_last_call_id(self, session_id: str, call_id: str) -> None:
        """Replace the call_id of the most recent decision history entry.

        Args:
            session_id: Unique session identifier.
            call_id: The real call_id to replace the placeholder.
        """
        with self._lock:
            state = self._sessions.get(session_id)
            if state is not None and state.decision_history:
                state.decision_history[-1]["call_id"] = call_id

    def exceeds_rate_limit(
        self, session_id: str, rate: float, burst: int
    ) -> tuple[bool, str | None]:
        """Check if a call exceeds the rate limit using token bucket.

        Args:
            session_id: Unique session identifier.
            rate: Calls allowed per second.
            burst: Maximum burst size (tokens in bucket).

        Returns:
            A tuple of ``(exceeded: bool, reason: str | None)``.
        """
        with self._lock:
            state = self._sessions.get(session_id)
            if state is None:
                return False, None
            now = time.monotonic()
            elapsed = now - state._last_bucket_fill
            state._bucket = min(burst, state._bucket + elapsed * rate)
            state._last_bucket_fill = now
            if state._bucket < 1.0:
                return True, f"rate limit exceeded ({rate}/s, burst {burst})"
            state._bucket -= 1.0
            return False, None
