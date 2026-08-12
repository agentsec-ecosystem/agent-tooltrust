"""Docker smoke test — build image, start container, verify health, stop."""

from __future__ import annotations

import subprocess
import time
import urllib.request

import pytest


class TestDockerSmoke:
    IMAGE = "tooltrust:latest"
    HEALTH_URL = "http://localhost:8000/audit/health"

    @pytest.fixture(scope="class")
    def _docker_setup(self) -> None:
        subprocess.run(["docker", "build", "-t", self.IMAGE, "."], check=True)
        subprocess.run(
            ["docker", "compose", "up", "--detach", "--wait"],
            check=True,
        )
        yield
        subprocess.run(["docker", "compose", "down"], check=True)

    def test_build_succeeds(self) -> None:
        result = subprocess.run(
            ["docker", "build", "-t", self.IMAGE, "."],
            capture_output=True, text=True,
        )
        assert result.returncode == 0

    def test_container_starts_and_healthy(self) -> None:
        subprocess.run(
            ["docker", "compose", "up", "--detach", "--wait"],
            check=True,
            timeout=30,
        )

        for _ in range(10):
            try:
                resp = urllib.request.urlopen(self.HEALTH_URL)
                if resp.status == 200:
                    break
            except Exception:
                time.sleep(1)

        resp = urllib.request.urlopen(self.HEALTH_URL)
        assert resp.status == 200
        import json
        data = json.loads(resp.read())
        assert data["status"] == "ok"
        assert data.get("uptime", 0) >= 0

    def test_health_endpoint(self) -> None:
        resp = urllib.request.urlopen(self.HEALTH_URL)
        assert resp.status == 200

    def test_cleanup(self) -> None:
        result = subprocess.run(
            ["docker", "compose", "down"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0