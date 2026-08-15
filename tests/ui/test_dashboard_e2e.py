# ruff: noqa: S310,S110
"""Playwright E2E tests for the M7.5 Operator Console / web dashboard.

These tests drive a real Chromium browser (headless) against the dashboard
served by the Docker container. Before running they POST ``/api/seed`` to
populate deterministic demo data (audit trail + escalations in every
lifecycle state), then exercise and screenshot every tab for the user guide.

Screenshots land in ``docs/reference/screenshots/`` (dedicated folder).

The whole suite is CI-gated and skips locally when:
  * ``TOOLTRUST_SKIP_UI`` is set, or
  * Playwright is not importable, or
  * Docker is unavailable, or
  * the dashboard container cannot be reached.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")

from playwright.sync_api import Page, ViewportSize, sync_playwright

DASHBOARD_URL = os.environ.get("TOOLTRUST_DASHBOARD_URL", "http://localhost:9000/dashboard")
BASE_URL = DASHBOARD_URL.rsplit("/", 1)[0]
SCREENSHOT_DIR = Path("docs/reference/screenshots")
VIEWPORT = ViewportSize(width=1440, height=900)


def _docker_available() -> bool:
    return subprocess.run(["docker", "version"], capture_output=True, check=False).returncode == 0


@pytest.fixture(scope="module")
def page():
    """Yield a Playwright page with demo data seeded and the dashboard loaded."""
    if os.environ.get("TOOLTRUST_SKIP_UI"):
        pytest.skip("TOOLTRUST_SKIP_UI is set; skipping UI E2E.")
    if not _docker_available():
        pytest.skip("docker CLI not available; skipping UI E2E.")

    up = subprocess.run(
        ["docker", "compose", "up", "--detach", "--force-recreate", "--wait"],
        capture_output=True, text=True,
    )
    if up.returncode != 0:
        pytest.skip(f"docker compose up failed:\n{up.stdout}\n{up.stderr}")

    _seed()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(viewport=VIEWPORT)
        pg = context.new_page()
        errors: list[str] = []
        pg.on("pageerror", lambda exc: errors.append(str(exc)))
        pg.on(
            "console",
            lambda msg: errors.append(f"console:{msg.text}") if msg.type == "error" else None,
        )
        pg.goto(DASHBOARD_URL, wait_until="domcontentloaded")
        pg.wait_for_timeout(1500)
        yield pg
        browser.close()


def _seed() -> None:
    import urllib.request

    req = urllib.request.Request(f"{BASE_URL}/api/seed", method="POST", data=b"{}")
    try:
        urllib.request.urlopen(req, timeout=10).read()
    except Exception:
        pass  # seeding is best-effort; tests assert on what renders


def _shot(page: Page, name: str) -> None:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SCREENSHOT_DIR / f"{name}.png"
    page.screenshot(path=str(path), full_page=False)
    assert path.is_file() and path.stat().st_size > 0


def _click_tab(page: Page, name: str) -> None:
    page.get_by_role("link", name=name).first.click()
    page.wait_for_timeout(1200)


class TestShell:
    def test_title_and_nav(self, page):
        assert page.get_by_text("ToolTrust Operator Console").first.is_visible()
        for tab in ("Escalations", "Audit", "Sessions", "Analytics", "Baselines", "Health"):
            assert page.get_by_role("link", name=tab).first.is_visible()

    def test_dashboard_screenshot(self, page):
        _shot(page, "ui-dashboard")


class TestEscalations:
    def test_pending_list_renders(self, page):
        assert page.get_by_text("Pending Escalations").first.is_visible()
        assert page.get_by_text("esc_pending_01").first.is_visible()

    def test_pending_escalation_screenshot(self, page):
        _shot(page, "ui-escalations-pending")

    def test_show_all_lists_every_state(self, page):
        page.get_by_role("button", name="Show All").click()
        page.wait_for_timeout(800)
        assert page.get_by_text("approved", exact=True).first.is_visible()
        assert page.get_by_text("denied", exact=True).first.is_visible()
        _shot(page, "ui-escalations-all")
        page.get_by_role("button", name="Pending Only").click()

    def test_approve_round_trip(self, page):
        page.get_by_role("button", name="Approve").first.click()
        page.wait_for_timeout(1000)
        assert page.get_by_text("Approved").first.is_visible()

    def test_deny_round_trip(self, page):
        page.on("dialog", lambda d: d.accept("blocked by reviewer"))
        page.get_by_role("button", name="Deny").first.click()
        page.wait_for_timeout(1000)
        assert page.get_by_text("Denied").first.is_visible()


class TestAudit:
    def test_audit_table_renders(self, page):
        _click_tab(page, "Audit")
        assert page.get_by_text("Audit Trail").first.is_visible()
        assert page.locator("table tbody tr").count() > 0

    def test_audit_screenshot(self, page):
        _shot(page, "ui-audit")


class TestSessions:
    def test_session_lookup(self, page):
        _click_tab(page, "Sessions")
        page.locator("#session-input").fill("demo-session")
        page.get_by_role("button", name="Load").click()
        page.wait_for_timeout(1200)
        assert page.get_by_text("demo-session").first.is_visible()

    def test_sessions_screenshot(self, page):
        _shot(page, "ui-sessions")


class TestAnalytics:
    def test_analytics_renders(self, page):
        _click_tab(page, "Analytics")
        assert page.get_by_text("Total Decisions").first.is_visible()

    def test_analytics_screenshot(self, page):
        _shot(page, "ui-analytics")


class TestBaselines:
    def test_baselines_renders(self, page):
        _click_tab(page, "Baselines")
        assert page.get_by_text("Security Baselines").first.is_visible()
        assert page.get_by_text("essential", exact=True).first.is_visible()

    def test_baselines_screenshot(self, page):
        _shot(page, "ui-baselines")


class TestHealth:
    def test_health_renders(self, page):
        _click_tab(page, "Health")
        assert page.get_by_text("Server Health").first.is_visible()

    def test_health_screenshot(self, page):
        _shot(page, "ui-health")
