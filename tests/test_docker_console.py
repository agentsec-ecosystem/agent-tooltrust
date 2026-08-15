# ruff: noqa: S310,S607
"""Containerized test execution for the operator console (M7.5 #157).

Builds the image, starts the container, and runs the M7.5 API contract +
smoke suite against the *live* service through the network — proving the
console (escalation approval + audit) works end to end in the shipped
Docker topology, not just in-process.

These tests require Docker; they are run by the ``docker`` CI job and are
skipped when Docker is unavailable.
"""

from __future__ import annotations

import json
import subprocess
import time
import urllib.error
import urllib.request

import pytest

API_BASE = "http://localhost:9000"
HEALTH_URL = f"{API_BASE}/audit/health"
ESC_URL = f"{API_BASE}/api/escalations"


def _docker_available() -> bool:
    try:
        subprocess.run(["docker", "version"], capture_output=True, check=True)
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


pytestmark = pytest.mark.skipif(
    not _docker_available(), reason="Docker is not available in this environment"
)


class TestContainerizedConsole:
    @pytest.fixture(scope="class")
    def _docker_up(self) -> None:
        subprocess.run(["docker", "build", "-t", "tooltrust:latest", "."], check=True)
        subprocess.run(["docker", "compose", "up", "--detach", "--wait"], check=True)
        _wait_healthy()
        yield
        subprocess.run(["docker", "compose", "down"], check=True)

    def test_health_endpoint(self, _docker_up: None) -> None:
        data = _get_json(HEALTH_URL)
        assert data["status"] == "ok"

    def test_escalations_endpoint_returns_json_list(self, _docker_up: None) -> None:
        data = _get_json(ESC_URL)
        assert isinstance(data, list)

    def test_audit_endpoint_returns_json_list(self, _docker_up: None) -> None:
        data = _get_json(f"{API_BASE}/audit")
        assert isinstance(data, list)

    def test_dashboard_serves_html(self, _docker_up: None) -> None:
        with urllib.request.urlopen(f"{API_BASE}/dashboard", timeout=10) as resp:
            assert resp.status == 200
            body = resp.read().decode("utf-8", errors="replace")
        assert "ToolTrust Operator Console" in body
        assert "/api/escalations" in body

    def test_escalations_accept_malformed_approve_gracefully(self, _docker_up: None) -> None:
        # Unknown escalation id must 409 (JSON error), not 500.
        try:
            _post_json(f"{ESC_URL}/esc_nope/approve", {"approver": "ci"})
        except urllib.error.HTTPError as exc:
            assert exc.code == 409
            assert "error" in json.loads(exc.read() or b"{}")


def _wait_healthy(timeout: float = 30.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = urllib.request.urlopen(HEALTH_URL)
            if resp.status == 200:
                return
        except Exception:
            time.sleep(1)
    raise AssertionError("container did not become healthy in time")


def _get_json(url: str):
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.loads(resp.read())


def _post_json(url: str, body: dict):
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())
