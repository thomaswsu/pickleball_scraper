"""Playwright end-to-end tests."""

from __future__ import annotations

import pytest
from playwright.sync_api import expect


@pytest.mark.e2e
@pytest.mark.playwright
@pytest.mark.skip_browser("webkit")
def test_dashboard_flow(page, e2e_base_url):
    """Verify that the dashboard renders data and handles alert CRUD."""

    page.goto(e2e_base_url)
    page.wait_for_load_state("domcontentloaded")

    expect(page.get_by_role("heading", name="Current Availability")).to_be_visible()
    expect(page.get_by_role("heading", name="Playwright Courts")).to_be_visible()

    label_input = page.get_by_placeholder("ex: Tuesday Doubles 9am")
    label_input.fill("Playwright Watch")
    page.get_by_placeholder("you@example.com").fill("playwright@example.com")
    page.get_by_role("button", name="Save alert").click()

    success_message = page.locator("#watch-form-message")
    expect(success_message).to_have_text("Alert saved!", timeout=5000)

    watch_card = page.locator("#watchers-list div.rounded-xl").first
    expect(watch_card).to_contain_text("Playwright Watch")
    expect(watch_card).to_contain_text("ACTIVE")

    watch_card.get_by_role("button", name="Pause").click()
    expect(watch_card).to_contain_text("PAUSED")

    page.locator("#filter-time-from").fill("23:00")
    expect(page.get_by_text("No open slots right now.")).to_be_visible()
    page.locator("#filter-reset").click()
    expect(page.get_by_role("heading", name="Playwright Courts")).to_be_visible()

    page.locator("#filter-date").fill("2099-01-01")
    expect(page.get_by_text("No open slots right now.")).to_be_visible()
    page.locator("#filter-reset").click()
    expect(page.get_by_role("heading", name="Playwright Courts")).to_be_visible()
