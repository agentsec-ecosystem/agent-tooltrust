"""Playwright E2E tests for the M7.5 Operator Console / web dashboard.

These tests drive a real Chromium browser (headless) against the dashboard
served by the Docker container on ``http://localhost:9000/dashboard`` and
capture screenshots for the user guides (docs/test/web-ui-test-plan.md §4.4/4.5).

The whole suite is CI-gated and skips locally when:
  * ``TOOLTRUST_SKIP_UI`` is set (opt-in skip), or
  * Playwright is not importable, or
  * Docker is unavailable, or
  * the dashboard container cannot be reached / rendered.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")

from playwright.sync_api import ViewportSize, sync_playwright

DASHBOARD_URL = os.environ.get("TOOLTRUST_DASHBOARD_URL", "http://localhost:9000/dashboard")
SCREENSHOT_DIR = Path("docs/reference")
VIEWPORT = ViewportSize(width=1440, height=900)


def _docker_available() -> bool:
    """Return True if the ``docker`` CLI is invocable on PATH."""
    return subprocess.run(
        ["docker", "version"],
        capture_output=True,
        check=False,
    ).returncode == 0


@pytest.fixture(scope="module")
def dashboard_page():
    """Yield a Playwright browser page pointed at the dashboard.

    Before the browser launches we ensure the Docker container is up
    (``docker compose up --wait``). Containers marked for deletion at teardown.
    """

    if os.environ.get("TOOLTRUST_SKIP_UI"):
        pytest.skip("TOOLTRUST_SKIP_UI is set; skipping UI E2E.")

    if not _docker_available():
        pytest.skip("docker CLI not available; skipping UI E2E.")

    up = subprocess.run(
        ["docker", "compose", "up", "--detach", "--force-recreate", "--wait"],
        capture_output=True,
        text=True,
    )
    if up.returncode != 0:
        pytest.skip(f"docker compose up failed:\n{up.stdout}\n{up.stderr}")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(viewport=VIEWPORT)
        page = context.new_page()
        page_errors: list[str] = []
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))
        page.on(
            "console",
            lambda msg: page_errors.append(f"console:{msg.text}") if msg.type == "error" else None,
        )
        page.goto(DASHBOARD_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
        yield page, page_errors
        browser.close()


def test_dashboard_title_and_nav_visible(dashboard_page):
    """J1/C1: the dashboard shell renders the console title and nav links."""
    page, _ = dashboard_page
    page.get_by_text("ToolTrust Operator Console").first.wait_for(timeout=10_000)
    assert page.get_by_text("ToolTrust Operator Console").first.is_visible()
    page.get_by_role("link", name="Escalations").first.wait_for(timeout=10_000)
    assert page.get_by_role("link", name="Escalations").first.is_visible()


def test_dashboard_screenshot(dashboard_page):
    """S1: capture the dashboard home screenshot for the user guide."""
    page, _ = dashboard_page
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SCREENSHOT_DIR / "ui-dashboard.png"
    page.screenshot(path=str(path), full_page=False)
    assert path.is_file() and path.stat().st_size > 0


def test_audit_tab_renders(dashboard_page):
    """C3: switching to the Audit tab renders the audit table (or empty state)."""
    page, _ = dashboard_page
    page.get_by_text("Audit", exact=True).first.click()
    page.wait_for_timeout(1500)
    # The audit table renders rows with the decision headers, or the empty-state
    # message when there is no data.
    page.get_by_text("Audit Trail").first.wait_for(timeout=10_000)
    assert page.get_by_text("Audit Trail").first.is_visible()
    has_rows = page.locator("table tbody tr").count() > 0
    has_descriptive_empty = page.get_by_text("No audit", exact=False).count() > 0
    assert has_rows or has_descriptive_empty, "audit panel is neither populated nor its empty state"


def test_audit_screenshot(dashboard_page):
    """S3: capture the audit viewer screenshot for the user guide."""
    page, _ = dashboard_page
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SCREENSHOT_DIR / "ui-audit.png"
    page.screenshot(path=str(path), full_page=False)
    assert path.is_file() and path.stat().st_size > 0


def test_no_page_errors(dashboard_page):
    """E3: the dashboard render produces no uncaught page / console errors."""
    _, page_errors = dashboard_page
    assert page_errors == [], f"page errors captured: {page_errors}"
