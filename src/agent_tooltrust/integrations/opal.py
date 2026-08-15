"""OPAL integration for distributed policy sync.

Connects to an OPAL server to receive policy updates and hot-reloads them
onto running Engine instances. Supports rollback to previous versions.

Usage:
    from agent_tooltrust.integrations.opal import OpalClient

    client = OpalClient(engine, server_url="https://opal.example.com")
    client.start()  # begins listening for policy updates
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from agent_tooltrust.policy.loader import load_policy


class OpalClient:
    """OPAL client that receives policy updates and hot-reloads the engine.

    Args:
        engine: The Engine instance to apply policy updates to.
        server_url: OPAL server URL (default: ``OPAL_SERVER_URL`` env var).
        policy_path: Local path for policy snapshots (default: tmpdir).
    """

    def __init__(
        self,
        engine: Any,
        server_url: str | None = None,
        policy_path: str | None = None,
    ) -> None:
        self._engine = engine
        self._server_url = server_url or os.environ.get("OPAL_SERVER_URL", "")
        self._policy_path = Path(policy_path or tempfile.mkdtemp(prefix="tooltrust_opal_"))
        self._policy_path.mkdir(parents=True, exist_ok=True)
        self._version_history: list[str] = []
        self._opal = None

    def start(self) -> None:
        """Connect to the OPAL server and begin listening for policy updates."""
        try:
            from opal_client.client import OpalClient as _OpalClient
        except ImportError:
            raise RuntimeError(
                "opal-client is not installed. Run: pip install agent-tooltrust[opal]"
            ) from None

        async def _on_policy_update(data: dict[str, Any]) -> None:
            self._apply_update(data)

        client = _OpalClient(
            server_url=self._server_url,
            callback=_on_policy_update,
        )
        self._opal = client
        client.start()

    def stop(self) -> None:
        """Disconnect from the OPAL server."""
        if self._opal is not None:
            self._opal.stop()

    def _apply_update(self, data: dict[str, Any]) -> None:
        """Apply a policy update from OPAL."""
        version = data.get("version", f"v{len(self._version_history)}")
        policy_data = data.get("policy", {})

        snapshot_path = self._policy_path / f"policy-{version}.yaml"
        with open(snapshot_path, "w") as f:
            json.dump(policy_data, f)

        policy = load_policy(str(snapshot_path))
        self._engine.reload_policy(policy)
        self._version_history.append(version)

    @property
    def versions(self) -> list[str]:
        """Return all policy versions seen by this client."""
        return list(self._version_history)

    def rollback(self, version: str) -> bool:
        """Rollback to a previous policy version.

        Args:
            version: The version string to roll back to.

        Returns:
            True if the rollback succeeded, False if the version is unknown.
        """
        if version not in self._version_history:
            return False
        snapshot_path = self._policy_path / f"policy-{version}.yaml"
        if not snapshot_path.exists():
            return False
        policy = load_policy(str(snapshot_path))
        self._engine.reload_policy(policy)
        return True
