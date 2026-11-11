"""Behave environment hooks for Lumen Accounting Suite BDD E2E test suite using Playwright."""

from __future__ import annotations

import re
from typing import Any
import urllib.request
import uuid
try:
    from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright
except ModuleNotFoundError:  # pragma: no cover - fallback when running via Selenium adapter
    Browser = BrowserContext = Page = Playwright = Any  # type: ignore[misc,assignment]
    sync_playwright = None  # type: ignore[assignment]

from features.config import (
    BASE_URL,
    CHROMIUM_BINARY,
    HEADLESS,
    HOST,
    PORT,
    SCREENSHOTS_DIR,
    USING_DOCKER_COMPOSE,
)
from features.pages.accounting_page import AccountingPage
from features.pages.base_page import BasePage
from features.pages.contacts_and_inventory_page import ContactsAndInventoryPage
from features.pages.dashboard_page import DashboardPage
from features.pages.expenses_and_admin_page import ExpensesAndAdminPage
from features.pages.payroll_and_assets_page import PayrollAndAssetsPage
from features.pages.reports_and_settings_page import ReportsAndSettingsPage
from features.pages.transactions_page import TransactionsPage
from features.pages.ux_patterns_page import UxPatternsPage
from features.support_server import start_background_server


def _attach_console_listeners(page: Page) -> None:
    """Attach console and pageerror listeners to record SEVERE browser errors."""
    setattr(page, "_severe_logs", [])

    def _on_console(msg) -> None:
        if msg.type == "error":
            text = msg.text or ""
            loc = msg.location or {}
            url = loc.get("url", "") if isinstance(loc, dict) else ""
            combined = f"{url} {text}".strip()
            if "favicon.ico" in combined:
                return
            if "Failed to load resource: the server responded with a status of 4" in combined:
                return
            getattr(page, "_severe_logs").append({"level": "SEVERE", "message": combined})

    def _on_pageerror(exc) -> None:
        getattr(page, "_severe_logs").append({"level": "SEVERE", "message": str(exc)})

    page.on("console", _on_console)
    page.on("pageerror", _on_pageerror)


def _build_playwright_page(pw: Playwright) -> tuple[Browser, BrowserContext, Page]:
    if sync_playwright is None or pw is None:
        from tests.js_runner import _get_playwright_page

        page = _get_playwright_page()
        page.set_viewport_size({"width": 1440, "height": 900})
        return None, None, page
    browser = pw.chromium.launch(
        executable_path=CHROMIUM_BINARY,
        headless=HEADLESS,
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-features=IsolateOrigins,site-per-process",
        ],
    )
    browser_context = browser.new_context(viewport={"width": 1440, "height": 900})
    page = browser_context.new_page()
    page.set_default_timeout(2000)
    page.set_default_navigation_timeout(15000)
    _attach_console_listeners(page)
    return browser, browser_context, page


def _ensure_page_alive(context) -> None:
    """Verify the Playwright page is responsive and recreate if a renderer tab crashed."""
    try:
        context.page.evaluate("() => document.readyState")
    except Exception:
        for attr, method in (("page", "close"), ("browser_context", "close"), ("browser", "close")):
            obj = getattr(context, attr, None)
            if obj is not None:
                try:
                    getattr(obj, method)()
                except Exception:
                    pass
        context.browser, context.browser_context, context.page = _build_playwright_page(
            context.playwright
        )


def before_all(context) -> None:
    """Ensure target server (Docker Compose stack or local support server) is healthy and launch Playwright."""
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    context.server = None if USING_DOCKER_COMPOSE else start_background_server(HOST, PORT)

    req = urllib.request.Request(BASE_URL, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/130.0.0.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        if resp.status != 200:
            raise RuntimeError(f"Pre-flight health check failed on {BASE_URL}: HTTP {resp.status}")

    context.playwright = sync_playwright().start() if sync_playwright is not None else None
    context.browser, context.browser_context, context.page = _build_playwright_page(
        context.playwright
    )
    context.base_url = BASE_URL


def before_scenario(context, scenario) -> None:
    """Initialize per-scenario isolated UUID suffix, resource tracker, and Page Objects."""
    _ensure_page_alive(context)
    context.scenario_uid = uuid.uuid4().hex[:8]
    context.created_resources = []
    context.console_errors = []

    context.base_page = BasePage(context.page, context.base_url)
    context.dashboard_page = DashboardPage(context.page, context.base_url)
    context.accounting_page = AccountingPage(context.page, context.base_url)
    context.contacts_page = ContactsAndInventoryPage(context.page, context.base_url)
    context.transactions_page = TransactionsPage(context.page, context.base_url)
    context.payroll_page = PayrollAndAssetsPage(context.page, context.base_url)
    context.reports_page = ReportsAndSettingsPage(context.page, context.base_url)
    context.expenses_admin_page = ExpensesAndAdminPage(context.page, context.base_url)
    context.ux_page = UxPatternsPage(context.page, context.base_url)


def after_step(context, step) -> None:
    """Monitor browser console for unexpected SEVERE errors after every step."""
    severe_logs = context.base_page.collect_severe_console_logs()
    if severe_logs:
        context.console_errors.extend(severe_logs)
        raise AssertionError(
            f"Unexpected browser console SEVERE error(s) during step '{step.name}': {severe_logs}"
        )


def after_scenario(context, scenario) -> None:
    """Capture scenario verification screenshot and perform guaranteed resource teardown."""
    try:
        context.base_page.dismiss_any_alert()
        slug = re.sub(r"[^a-z0-9]+", "_", scenario.name.lower()).strip("_")[:60]
        screenshot_path = SCREENSHOTS_DIR / f"{slug}.png"
        context.page.screenshot(path=str(screenshot_path), timeout=10000)
    except Exception:
        pass
    finally:
        try:
            if "responsive" in scenario.tags:
                context.page.set_viewport_size({"width": 1440, "height": 900})
            context.base_page.dismiss_modals_if_present()
            context.base_page.cleanup_created_resources(context.created_resources)
        except Exception:
            pass


def after_all(context) -> None:
    """Close Playwright browser and stop embedded HTTP server if started by this run."""
    for attr, method in (
        ("page", "close"),
        ("browser_context", "close"),
        ("browser", "close"),
        ("playwright", "stop"),
    ):
        obj = getattr(context, attr, None)
        if obj is not None:
            try:
                getattr(obj, method)()
            except Exception:
                pass
    if getattr(context, "server", None):
        context.server.shutdown()
