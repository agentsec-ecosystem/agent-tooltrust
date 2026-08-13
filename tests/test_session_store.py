"""Tests for the SessionStore — in-memory session state tracking."""

from __future__ import annotations

import uuid

import pytest

from agent_tooltrust.server.session_store import SessionState, SessionStore


class TestSessionState:
    """SessionState dataclass construction and defaults."""

    def test_construction_with_minimal_args(self) -> None:
        state = SessionState(session_id="sess_1")

        assert state.session_id == "sess_1"
        assert state.risk_score == 0.0
        assert state.tool_call_count == 0
        assert state.token_budget is None
        assert state.call_budget is None
        assert state.consent_scopes == []
        assert state.decision_history == []
        assert state.created_at > 0
        assert state.last_updated > 0

    def test_construction_with_budgets(self) -> None:
        state = SessionState(
            session_id="sess_1", token_budget=10000, call_budget=50
        )

        assert state.token_budget == 10000
        assert state.call_budget == 50

    def test_construction_with_consent_scopes(self) -> None:
        scopes = [{"tool": "query_logs", "env": "staging", "data_class": "internal"}]
        state = SessionState(session_id="sess_1", consent_scopes=scopes)

        assert state.consent_scopes == scopes


class TestSessionStore:
    """SessionStore CRUD and enforcement."""

    @pytest.fixture
    def store(self) -> SessionStore:
        return SessionStore()

    def test_get_or_create_creates_new_session(self, store: SessionStore) -> None:
        state = store.get_or_create("sess_new")

        assert state.session_id == "sess_new"
        assert state.risk_score == 0.0
        assert state.tool_call_count == 0

    def test_get_or_create_returns_existing(self, store: SessionStore) -> None:
        state1 = store.get_or_create("sess_1")
        state2 = store.get_or_create("sess_1")

        assert state1 is state2

    def test_get_returns_none_for_missing(self, store: SessionStore) -> None:
        assert store.get("nonexistent") is None

    def test_get_returns_existing(self, store: SessionStore) -> None:
        state = store.get_or_create("sess_1")
        assert store.get("sess_1") is state

    def test_update_accumulates_risk_and_count(self, store: SessionStore) -> None:
        call_id = str(uuid.uuid4())
        store.get_or_create("sess_1")

        state = store.update("sess_1", risk_increment=0.5, call_id=call_id)

        assert state.risk_score == 0.5
        assert state.tool_call_count == 1
        assert state.last_updated > state.created_at

        state = store.update("sess_1", risk_increment=0.3, call_id=str(uuid.uuid4()))

        assert state.risk_score == pytest.approx(0.8)
        assert state.tool_call_count == 2

    def test_update_records_decision_history(self, store: SessionStore) -> None:
        store.get_or_create("sess_1")
        call_id = str(uuid.uuid4())

        store.update("sess_1", risk_increment=0.2, call_id=call_id)
        state = store.get("sess_1")

        assert state is not None
        assert len(state.decision_history) == 1
        assert state.decision_history[0]["call_id"] == call_id
        assert state.decision_history[0]["risk_increment"] == 0.2

    def test_decision_history_rolling_window(self, store: SessionStore) -> None:
        store.get_or_create("sess_1")

        for _ in range(60):
            store.update("sess_1", risk_increment=0.01, call_id=str(uuid.uuid4()))

        state = store.get("sess_1")
        assert state is not None
        assert len(state.decision_history) == 50

    def test_update_raises_for_missing_session(self, store: SessionStore) -> None:
        with pytest.raises(KeyError, match="sess_missing"):
            store.update("sess_missing", risk_increment=0.1, call_id="c1")

    def test_exceeds_budget_call_count(self, store: SessionStore) -> None:
        store.get_or_create("sess_1", call_budget=3)
        store.update("sess_1", risk_increment=0.1, call_id="c1")
        store.update("sess_1", risk_increment=0.1, call_id="c2")
        store.update("sess_1", risk_increment=0.1, call_id="c3")

        # Budget of 3 authorizes exactly 3 calls; the 4th exceeds it.
        exceeded, reason = store.exceeds_budget("sess_1")
        assert not exceeded

        store.update("sess_1", risk_increment=0.1, call_id="c4")
        exceeded, reason = store.exceeds_budget("sess_1")
        assert exceeded
        assert reason is not None
        assert "call" in reason.lower()

    def test_exceeds_budget_under_limit(self, store: SessionStore) -> None:
        store.get_or_create("sess_1", call_budget=10)
        store.update("sess_1", risk_increment=0.1, call_id="c1")

        exceeded, _ = store.exceeds_budget("sess_1")
        assert not exceeded

    def test_exceeds_budget_no_budget_set(self, store: SessionStore) -> None:
        store.get_or_create("sess_1")
        store.update("sess_1", risk_increment=0.1, call_id="c1")

        exceeded, _ = store.exceeds_budget("sess_1")
        assert not exceeded

    def test_within_consent_matching_scope(self, store: SessionStore) -> None:
        store.get_or_create(
            "sess_1",
            consent_scopes=[{"tool": "query_logs", "env": "staging", "data_class": "internal"}],
        )

        assert store.within_consent("sess_1", "query_logs", "staging", "internal")

    def test_within_consent_mismatch_tool(self, store: SessionStore) -> None:
        store.get_or_create(
            "sess_1",
            consent_scopes=[{"tool": "query_logs", "env": "staging", "data_class": "internal"}],
        )

        assert not store.within_consent("sess_1", "deploy_service", "staging", "internal")

    def test_within_consent_no_scopes_set(self, store: SessionStore) -> None:
        store.get_or_create("sess_1")
        assert store.within_consent("sess_1", "any_tool", "any_env", "any_data")

    def test_within_consent_wildcard_env(self, store: SessionStore) -> None:
        store.get_or_create(
            "sess_1",
            consent_scopes=[{"tool": "query_logs", "env": "*", "data_class": "internal"}],
        )
        assert store.within_consent("sess_1", "query_logs", "production", "internal")

    def test_list_sessions(self, store: SessionStore) -> None:
        store.get_or_create("sess_a")
        store.get_or_create("sess_b")

        sessions = store.list_sessions()
        assert "sess_a" in sessions
        assert "sess_b" in sessions
        assert len(sessions) == 2

    def test_thread_safety(self, store: SessionStore) -> None:
        import threading

        errors: list[Exception] = []

        def worker(sid: str) -> None:
            try:
                store.get_or_create(sid)
                for _ in range(50):
                    store.update(sid, risk_increment=0.01, call_id=str(uuid.uuid4()))
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(f"sess_{i}",)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0

    def test_get_or_create_with_budgets(self, store: SessionStore) -> None:
        state = store.get_or_create("sess_1", call_budget=5, token_budget=1000)
        assert state.call_budget == 5
        assert state.token_budget == 1000

    def test_get_or_create_with_consent_scopes(self, store: SessionStore) -> None:
        scopes = [{"tool": "t1", "env": "e1", "data_class": "d1"}]
        state = store.get_or_create("sess_1", consent_scopes=scopes)
        assert state.consent_scopes == scopes
