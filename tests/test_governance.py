"""Tests for governance reports and tamper-evident audit chain."""

from __future__ import annotations

from agent_tooltrust.audit.models import AuditEntry
from agent_tooltrust.audit.tamper_proof import (
    build_hash_chain,
    sign_root,
    verify_chain,
    verify_signature,
)


class TestTamperProof:
    def test_build_chain_produces_linked_hashes(self) -> None:
        entries = [
            AuditEntry(session_id="s1", timestamp="2026-01-01T00:00:00", tool="t1",
                       tool_category=None, action="read", action_class="read",
                       environment="staging", data_class="public", agent_id="a1",
                       agent_class=None, decision="allow", criticality="low",
                       reason_code="ok", explanation="ok"),
            AuditEntry(session_id="s1", timestamp="2026-01-01T00:01:00", tool="t2",
                       tool_category=None, action="write", action_class="write",
                       environment="staging", data_class="public", agent_id="a1",
                       agent_class=None, decision="allow", criticality="low",
                       reason_code="ok", explanation="ok"),
        ]
        chained = build_hash_chain(entries)
        assert len(chained) == 2
        assert chained[0].get("chain_hash") is not None
        assert chained[1].get("chain_hash") is not None
        assert chained[0].get("prev_hash") is None
        assert chained[1].get("prev_hash") == chained[0]["chain_hash"]

    def test_verify_chain_passes_for_clean_chain(self) -> None:
        entries = [
            AuditEntry(session_id="s1", timestamp="2026-01-01T00:00:00", tool="t1",
                       tool_category=None, action="read", action_class="read",
                       environment="staging", data_class="public", agent_id="a1",
                       agent_class=None, decision="allow", criticality="low",
                       reason_code="ok", explanation="ok"),
        ]
        chained = build_hash_chain(entries)
        result = verify_chain(chained)
        assert result["valid"]

    def test_verify_chain_fails_for_modified_entry(self) -> None:
        entries = [
            AuditEntry(session_id="s1", timestamp="2026-01-01T00:00:00", tool="t1",
                       tool_category=None, action="read", action_class="read",
                       environment="staging", data_class="public", agent_id="a1",
                       agent_class=None, decision="allow", criticality="low",
                       reason_code="ok", explanation="ok"),
        ]
        chained = build_hash_chain(entries)
        chained[0]["decision"] = "deny"
        result = verify_chain(chained)
        assert not result["valid"]
        assert result.get("tampered_index") is not None

    def test_sign_and_verify_root(self) -> None:
        entries = [
            AuditEntry(session_id="s1", timestamp="2026-01-01T00:00:00", tool="t1",
                       tool_category=None, action="read", action_class="read",
                       environment="staging", data_class="public", agent_id="a1",
                       agent_class=None, decision="allow", criticality="low",
                       reason_code="ok", explanation="ok"),
        ]
        chained = build_hash_chain(entries)
        signed = sign_root(chained)
        assert "signature" in signed
        assert verify_signature(signed)

    def test_verify_signature_fails_for_forged(self) -> None:
        entries = [
            AuditEntry(session_id="s1", timestamp="2026-01-01T00:00:00", tool="t1",
                       tool_category=None, action="read", action_class="read",
                       environment="staging", data_class="public", agent_id="a1",
                       agent_class=None, decision="allow", criticality="low",
                       reason_code="ok", explanation="ok"),
        ]
        chained = build_hash_chain(entries)
        signed = sign_root(chained)
        signed["signature"] = signed["signature"][:-4] + "xxxx"
        assert not verify_signature(signed)
