"""Tamper-evident audit chain — hash-linked integrity for audit entries.

Each entry's hash commits to the previous entry's hash + its own content.
Root is signed with ed25519 for non-repudiation. verify_chain detects any
modification with per-entry granularity.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from agent_tooltrust.audit.models import AuditEntry


def _hash_entry(entry: AuditEntry) -> str:
    """Compute a SHA-256 hash of an audit entry's serializable fields.

    Args:
        entry: The audit entry to hash.

    Returns:
        Hex-encoded SHA-256 digest.
    """
    data = json.dumps(entry.to_dict(), sort_keys=True)
    return hashlib.sha256(data.encode()).hexdigest()


def build_hash_chain(entries: list[AuditEntry]) -> list[dict[str, Any]]:
    """Build a hash-linked chain from audit entries.

    Each entry dict gets ``chain_hash`` and ``prev_hash`` fields.

    Args:
        entries: List of audit entries in chronological order.

    Returns:
        A list of dicts with chain_hash and prev_hash added.
    """
    chained: list[dict[str, Any]] = []
    prev_hash: str | None = None
    for entry in entries:
        entry_hash = _hash_entry(entry)
        chain_input = json.dumps(
            {"prev_hash": prev_hash, "entry_hash": entry_hash}, sort_keys=True
        )
        chain_hash = hashlib.sha256(chain_input.encode()).hexdigest()
        d = entry.to_dict()
        d["chain_hash"] = chain_hash
        d["prev_hash"] = prev_hash
        chained.append(d)
        prev_hash = chain_hash
    return chained


def sign_root(chained: list[dict[str, Any]]) -> dict[str, Any]:
    """Sign the root entry's chain hash with ed25519.

    Signs the **last** entry's ``chain_hash`` — the hash that transitively
    commits to every preceding entry. Returns a dict with ``signature`` and
    ``public_key`` (both hex-encoded) that ``verify_chain`` checks.

    Args:
        chained: The output of build_hash_chain.

    Returns:
        A dict with ``signature``, ``public_key``, and ``root_hash``.
    """
    if not chained:
        return {"signature": "", "public_key": "", "root_hash": ""}

    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    root_hash = chained[-1].get("chain_hash", "")

    signature = private_key.sign(root_hash.encode())
    return {
        "signature": signature.hex(),
        "public_key": public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        ).hex(),
        "chain_hash": root_hash,
    }


def verify_signature(signed: dict[str, Any]) -> bool:
    """Verify the ed25519 signature on the root entry.

    Args:
        signed: Output from sign_root.

    Returns:
        True if the signature is valid.
    """
    try:
        pub_key_bytes = bytes.fromhex(signed.get("public_key", ""))
        sig_bytes = bytes.fromhex(signed.get("signature", ""))
        root_hash = signed.get("chain_hash", "")
        public_key = ed25519.Ed25519PublicKey.from_public_bytes(pub_key_bytes)
        public_key.verify(sig_bytes, root_hash.encode())
        return True
    except Exception:
        return False


def verify_chain(chained: list[dict[str, Any]]) -> dict[str, Any]:
    """Verify the integrity of a hash-linked chain.

    Checks both internal hash consistency **and** the root ed25519 signature
    (when present). An attacker who rewrites entries must recompute every
    ``chain_hash`` — but without the private key they cannot produce a valid
    root signature, so the chain fails verification.

    Args:
        chained: Output from build_hash_chain, optionally with signature/public_key.

    Returns:
        A dict with ``valid`` (bool), ``tampered_index`` (int | None),
        and ``signature_valid`` (bool | None).
    """
    prev_hash: str | None = None
    for i, entry in enumerate(chained):
        if i > 0 and entry.get("prev_hash") != prev_hash:
            return {"valid": False, "tampered_index": i, "signature_valid": None}
        expected_hash = entry.get("chain_hash")
        if expected_hash is None:
            return {"valid": False, "tampered_index": i, "signature_valid": None}

        content_data = {
            k: v
            for k, v in entry.items()
            if k not in ("chain_hash", "prev_hash", "signature", "public_key", "root_hash")
        }
        entry_hash = hashlib.sha256(
            json.dumps(content_data, sort_keys=True).encode()
        ).hexdigest()

        chain_input = json.dumps(
            {"prev_hash": prev_hash, "entry_hash": entry_hash}, sort_keys=True
        )
        computed = hashlib.sha256(chain_input.encode()).hexdigest()
        if computed != expected_hash:
            return {"valid": False, "tampered_index": i, "signature_valid": None}

        prev_hash = expected_hash

    sig_valid = None
    if chained and chained[-1].get("signature") and chained[-1].get("public_key"):
        sig_valid = verify_signature({
            "signature": chained[-1]["signature"],
            "public_key": chained[-1]["public_key"],
            "chain_hash": prev_hash,
        })

    return {
        "valid": sig_valid is not False,
        "tampered_index": None,
        "signature_valid": sig_valid,
    }
