"""Behave environment hooks for Lumen Accounting Suite BDD E2E test suite."""

from __future__ import annotations

import re
import urllib.request
import uuid
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

from features.config import (
    BASE_URL,
    CHROMEDRIVER_BINARY,
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


def _build_chrome_driver() -> webdriver.Chrome:
    options = Options()
    options.binary_location = CHROMIUM_BINARY
    if HEADLESS:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-features=IsolateOrigins,site-per-process")
    options.add_argument("--window-size=1440,900")
    options.set_capability("goog:loggingPrefs", {"browser": "ALL"})
    service = Service(executable_path=CHROMEDRIVER_BINARY)
    return webdriver.Chrome(service=service, options=options)


def _ensure_driver_alive(context) -> None:
    """Verify the browser session is responsive and recreate if a renderer tab crashed."""
    try:
        context.driver.execute_script("return document.readyState;")
    except Exception:
        try:
            context.driver.quit()
        except Exception:
            pass
        context.driver = _build_chrome_driver()


def before_all(context) -> None:
    """Ensure target server (Docker Compose stack or local support server) is healthy and launch browser."""
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    context.server = None if USING_DOCKER_COMPOSE else start_background_server(HOST, PORT)

    req = urllib.request.Request(BASE_URL, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/130.0.0.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        if resp.status != 200:
            raise RuntimeError(f"Pre-flight health check failed on {BASE_URL}: HTTP {resp.status}")

    context.driver = _build_chrome_driver()
    context.base_url = BASE_URL


def before_scenario(context, scenario) -> None:
    """Initialize per-scenario isolated UUID suffix, resource tracker, and Page Objects."""
    _ensure_driver_alive(context)
    context.scenario_uid = uuid.uuid4().hex[:8]
    context.created_resources = []
    context.console_errors = []

    context.base_page = BasePage(context.driver, context.base_url)
    context.dashboard_page = DashboardPage(context.driver, context.base_url)
    context.accounting_page = AccountingPage(context.driver, context.base_url)
    context.contacts_page = ContactsAndInventoryPage(context.driver, context.base_url)
    context.transactions_page = TransactionsPage(context.driver, context.base_url)
    context.payroll_page = PayrollAndAssetsPage(context.driver, context.base_url)
    context.reports_page = ReportsAndSettingsPage(context.driver, context.base_url)
    context.expenses_admin_page = ExpensesAndAdminPage(context.driver, context.base_url)
    context.ux_page = UxPatternsPage(context.driver, context.base_url)


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
        context.driver.save_screenshot(str(screenshot_path))
    except Exception:
        pass
    finally:
        try:
            if "responsive" in scenario.tags:
                context.driver.set_window_size(1440, 900)
            context.base_page.dismiss_modals_if_present()
            context.base_page.cleanup_created_resources(context.created_resources)
        except Exception:
            pass


def after_all(context) -> None:
    """Close browser and stop embedded HTTP server if started by this run."""
    if getattr(context, "driver", None):
        context.driver.quit()
    if getattr(context, "server", None):
        context.server.shutdown()
