"""Base Page Object encapsulating atomic explicit waits, navigation, alerts, and teardown."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable
from selenium.common.exceptions import (
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
    UnexpectedAlertPresentException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support.ui import Select, WebDriverWait

from features.config import DEFAULT_TIMEOUT_SECONDS, POLL_FREQUENCY_SECONDS, SCREENSHOTS_DIR


class BasePage:
    """Driver-agnostic base adapter with retry-aware wait predicates and teardown helpers."""

    MODAL_IDS = (
        "duplicateInvoiceModal",
        "invoiceModal",
        "editLedgerModal",
        "editAssetModal",
        "editAccrualModal",
        "matchPaymentModal",
        "matchInvoiceToPaymentModal",
        "expenseBreakdownModal",
        "accrualScheduleModal",
        "bankLedgerModal",
        "timesheetModal",
        "coaModal",
        "addEmployeeModal",
        "bankRuleModal",
    )

    VIEW_TARGET_MAP = {
        "Dashboard": "view-dashboard",
        "Banking": "view-bank",
        "Cheque Registry": "view-cheques",
        "Quotes & Estimates": "view-quotes",
        "Sales Invoices": "view-customer",
        "Purchase Orders": "view-po",
        "Supplier Bills": "view-supplier",
        "Expenses": "view-expense",
        "Chart of Accounts": "view-coa",
        "Journal Entries": "view-journal",
        "General Ledger": "view-ledger",
        "SOA": "view-statement",
        "Statement of Account": "view-statement",
        "Accruals": "view-accrual",
        "Recurring Transactions": "view-recurring",
        "Customers": "view-customer-list",
        "Suppliers": "view-supplier-list",
        "Inventory Directory": "view-inventory",
        "Stock Ledger": "view-stock-ledger",
        "Assets Directory": "view-assets",
        "Employee details": "view-employee-list",
        "Timesheet & WPS": "view-timesheet",
        "VAT": "view-tax",
        "Tax Reports": "view-tax",
        "Corporate Tax": "view-corp-tax",
        "Budgeting vs. Actuals": "view-budgeting",
        "Cash Flow Forecast": "view-cashflow-forecast",
        "Profit & Loss": "view-income-statement",
        "Balance Sheet": "view-balance-sheet",
        "Cash Flow": "view-cashflow",
        "Statement of Equity": "view-equity-statement",
        "Trial Balance": "view-trial",
        "Audit Log": "view-audit",
        "Settings": "view-settings",
    }

    def __init__(self, driver: WebDriver, base_url: str) -> None:
        self.driver = driver
        self.base_url = base_url

    def wait_until(
        self,
        predicate: Callable[[WebDriver], Any],
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> Any:
        """Execute an atomic predicate inside a retry-aware WebDriverWait."""
        wait = WebDriverWait(
            self.driver,
            timeout,
            poll_frequency=POLL_FREQUENCY_SECONDS,
            ignored_exceptions=(NoSuchElementException, StaleElementReferenceException),
        )
        return wait.until(predicate)

    def open_application(self) -> None:
        """Navigate to the application root and wait for initialization."""
        self.driver.get(self.base_url)
        self.wait_until(
            lambda d: d.execute_script("return document.readyState === 'complete'")
        )
        if self.driver.execute_script(
            "return Boolean(window.LumenProfiles && (!window.LumenProfiles.isAuthenticated() || !window.LumenProfiles.isOwner()));"
        ):
            self.driver.execute_script(
                "window.LumenProfiles.signIn(window.LumenProfiles.OWNER_ACCOUNT);"
            )
            self.driver.get(self.base_url)
            self.wait_until(
                lambda d: d.execute_script("return document.readyState === 'complete'")
            )
        self.wait_until(
            lambda d: d.find_element(By.ID, "view-dashboard").is_displayed()
        )
        self.collect_severe_console_logs()

    def open_unauthenticated_root(self) -> str:
        """Sign out any active session, open `/`, and wait for redirect to `/welcome`."""
        self.driver.get(f"{self.base_url}/welcome")
        self.wait_until(
            lambda d: d.execute_script("return document.readyState === 'complete'")
        )
        self.driver.execute_script(
            "if (window.LumenProfiles) window.LumenProfiles.signOut();"
        )
        self.driver.get(self.base_url)
        self.wait_until(
            lambda d: "/welcome" in d.current_url
            and d.execute_script("return document.readyState === 'complete'")
            and d.find_element(By.ID, "btnOpenSignIn").is_displayed()
        )
        self.collect_severe_console_logs()
        return self.driver.current_url

    def register_account_on_welcome(
        self,
        *,
        company_name: str,
        email: str,
        password: str,
        plan_id: str = "premium",
        card_number: str = "4242 4242 4242 4242",
        card_expiry: str = "12/28",
        card_cvv: str = "123",
    ) -> None:
        """Register a new company profile and account from the `/welcome` page."""
        self.click_id(f"btnChoose-{plan_id}")
        self.wait_until(lambda d: d.find_element(By.ID, "setupModal").is_displayed())
        self.fill_input("setupCompanyName", company_name)
        self.fill_input("setupEmail", email)
        self.fill_input("setupPassword", password)
        self.fill_input("setupPasswordConfirm", password)
        self.fill_input("setupCardName", company_name)
        self.fill_input("setupCardNumber", card_number)
        self.fill_input("setupCardExpiry", card_expiry)
        self.fill_input("setupCardCvv", card_cvv)
        self.click_id("btnSetupSubmit")
        self.wait_until(
            lambda d: d.find_element(By.ID, "view-dashboard").is_displayed()
        )
        self.collect_severe_console_logs()

    def sign_out_from_topbar(self) -> str:
        """Click `#btnTopbarSignOut` and wait for redirect to `/welcome`."""
        self.click_id("btnTopbarSignOut")
        self.wait_until(
            lambda d: "/welcome" in d.current_url
            and d.find_element(By.ID, "btnOpenSignIn").is_displayed()
        )
        self.collect_severe_console_logs()
        return self.driver.current_url

    def submit_sign_in_on_welcome(self, email: str, password: str) -> None:
        """Open the Sign-in modal on `/welcome` if hidden and submit credentials."""
        def _ensure_modal_open(d: WebDriver) -> bool:
            modal = d.find_element(By.ID, "signInModal")
            if not modal.is_displayed():
                btn = d.find_element(By.ID, "btnOpenSignIn")
                d.execute_script("arguments[0].click();", btn)
            return modal.is_displayed()

        self.wait_until(_ensure_modal_open)
        self.fill_input("signInEmail", email)
        self.fill_input("signInPassword", password)
        self.click_id("btnSignInSubmit")

    def get_sign_in_error_text(self) -> str:
        """Return the validation/authentication error message inside `#signInError`."""
        return self.wait_until(
            lambda d: d.find_element(By.ID, "signInError").text.strip()
        )

    def get_topbar_user_name(self) -> str:
        """Return the displayed `.user-profile .user-name` text."""
        return self.wait_until(
            lambda d: d.find_element(By.CSS_SELECTOR, ".user-profile .user-name").text.strip()
        )

    def navigate_to_view(self, view_label: str) -> str:
        """Click the sidebar navigation link for `view_label` and wait for its view container."""
        target_id = self.VIEW_TARGET_MAP.get(view_label, view_label)

        def _click_and_verify(d: WebDriver) -> bool:
            nav_el = d.find_element(By.CSS_SELECTOR, f'.nav-item[data-target="{target_id}"]')
            d.execute_script("arguments[0].click();", nav_el)
            view_el = d.find_element(By.ID, target_id)
            return view_el.is_displayed()

        self.wait_until(_click_and_verify)
        return target_id

    def get_active_page_title(self) -> str:
        """Return the text of `#pageTitle`."""
        return self.wait_until(
            lambda d: d.find_element(By.ID, "pageTitle").text.strip()
        )

    def toggle_language(self) -> None:
        """Click the topbar language switcher button (`#btnLangToggle`)."""
        self.click_id("btnLangToggle")

    def get_document_lang_and_dir(self) -> tuple[str, str]:
        """Return `(lang, dir)` attributes of `document.documentElement`."""
        res = self.driver.execute_script(
            "return [document.documentElement.lang || '', document.documentElement.dir || ''];"
        )
        return str(res[0]), str(res[1])

    def get_welcome_hero_heading(self) -> str:
        """Return the main hero `<h1>` text on `/welcome`."""
        return self.wait_until(
            lambda d: d.find_element(By.CSS_SELECTOR, "main .hero h1").text.strip()
        )

    def get_welcome_pricing_plans(self) -> list[dict[str, str]]:
        """Return the rendered plan cards (`title`, `amount`, `promo`) inside `#plans` on `/welcome`."""
        plans_el = self.wait_until(lambda d: d.find_element(By.ID, "plans"))
        cards = plans_el.find_elements(By.CSS_SELECTOR, ".plan")
        results: list[dict[str, str]] = []
        for card in cards:
            title_els = card.find_elements(By.TAG_NAME, "h2")
            amount_els = card.find_elements(By.CSS_SELECTOR, ".plan-price .amount")
            promo_els = card.find_elements(By.CSS_SELECTOR, ".plan-promo-pill")
            results.append({
                "title": title_els[0].text.strip() if title_els else "",
                "amount": amount_els[0].text.strip() if amount_els else "",
                "promo": promo_els[0].text.strip() if promo_els else "",
            })
        return results

    def is_view_displayed(self, view_id: str) -> bool:
        """Return True when `#<view_id>` is visible."""
        return bool(
            self.wait_until(lambda d: d.find_element(By.ID, view_id).is_displayed())
        )

    def fill_input(self, element_id: str, value: str) -> None:
        """Clear and populate an input element by ID."""
        def _fill(d: WebDriver) -> bool:
            el = d.find_element(By.ID, element_id)
            if el.get_attribute("type") in ("date", "month") or el.get_attribute("readonly"):
                d.execute_script(
                    "arguments[0].value = arguments[1];"
                    "arguments[0].dispatchEvent(new Event('input', {bubbles: true}));"
                    "arguments[0].dispatchEvent(new Event('change', {bubbles: true}));",
                    el,
                    str(value),
                )
            else:
                d.execute_script("arguments[0].removeAttribute('list');", el)
                el.clear()
                el.send_keys(str(value))
                d.execute_script(
                    "arguments[0].dispatchEvent(new Event('input', {bubbles: true}));"
                    "arguments[0].dispatchEvent(new Event('change', {bubbles: true}));",
                    el,
                )
            return True

        self.wait_until(_fill)

    def select_by_value_or_text(self, element_id: str, option_text_or_value: str) -> None:
        """Select a `<select>` option by visible text or value attribute."""
        def _select(d: WebDriver) -> bool:
            el = d.find_element(By.ID, element_id)
            sel = Select(el)
            for opt in sel.options:
                if opt.get_attribute("value") == option_text_or_value or opt.text.strip() == option_text_or_value:
                    sel.select_by_visible_text(opt.text)
                    d.execute_script(
                        "arguments[0].dispatchEvent(new Event('change', {bubbles: true}));",
                        el,
                    )
                    return True
            return False

        self.wait_until(_select)

    def click_id(self, element_id: str) -> None:
        """Click an element by ID using atomic lookup."""
        def _click(d: WebDriver) -> bool:
            el = d.find_element(By.ID, element_id)
            d.execute_script("arguments[0].click();", el)
            return True

        self.wait_until(_click)

    def get_text_by_id(self, element_id: str) -> str:
        """Return stripped text content of an element by ID."""
        return self.wait_until(
            lambda d: (d.find_element(By.ID, element_id).text.strip(),)
        )[0]

    def get_value_by_id(self, element_id: str) -> str:
        """Return the `.value` attribute of an input/select element by ID."""
        return self.wait_until(
            lambda d: ((d.find_element(By.ID, element_id).get_attribute("value") or "").strip(),)
        )[0]

    def post_latest_ledger_entry(self) -> None:
        """Transition the most recently saved ledger entry to 'posted' status via `handleLedgerAction`."""
        self.driver.execute_script(
            """
            const raw = localStorage.getItem('bookkeeping_history_v2');
            if (!raw) return;
            const history = JSON.parse(raw);
            if (Array.isArray(history) && history.length > 0) {
                const latest = history[0];
                if (latest && latest.id && typeof window.handleLedgerAction === 'function') {
                    window.handleLedgerAction(latest.id, 'post');
                }
            }
            """
        )

    # In-app feedback (ui-feedback.js): styled confirm/prompt dialogs and toasts replace native dialogs.
    _FEEDBACK_PROBE_JS = """
        const [accept] = arguments;
        const dialog = document.querySelector('.lumen-dialog-backdrop .lumen-dialog');
        if (dialog) {
            const pick = (sel) => dialog.querySelector(sel);
            const text = (pick('.lumen-dialog__message') || pick('.lumen-dialog__title')).textContent.trim();
            const btn = accept ? pick('[data-dialog-action="confirm"]')
                : (pick('[data-dialog-action="cancel"]') || pick('[data-dialog-action="confirm"]'));
            btn.click();
            return { kind: 'dialog', text };
        }
        const toasts = Array.from(document.querySelectorAll('#lumenToastRegion .lumen-toast:not([data-leaving])'));
        if (toasts.length === 0) return null;
        const latest = toasts[toasts.length - 1];
        toasts.forEach((t) => t.querySelector('.lumen-toast__close').click());
        return { kind: 'toast', text: latest.querySelector('.lumen-toast__message').textContent.trim() };
    """

    def accept_alert_if_present(self, timeout: float = 3.0) -> str | None:
        """Wait for in-app feedback: confirm any styled dialog(s), read and dismiss toasts, and return the last text."""
        last_text: str | None = None
        current_timeout = timeout
        while True:
            try:
                result = WebDriverWait(self.driver, current_timeout, poll_frequency=0.05).until(
                    lambda d: d.execute_script(self._FEEDBACK_PROBE_JS, True)
                )
            except TimeoutException:
                break
            last_text = result.get("text")
            current_timeout = 0.6
        return last_text

    def read_feedback_message(self, timeout: float = 3.0) -> str | None:
        """Alias with intent-revealing name for steps that only read a toast message."""
        return self.accept_alert_if_present(timeout=timeout)

    def dismiss_any_alert(self) -> None:
        """Idempotently cancel any open in-app dialog and dismiss visible toasts (never confirms)."""
        for _ in range(3):
            try:
                if not self.driver.execute_script(self._FEEDBACK_PROBE_JS, False):
                    break
            except Exception:
                break

    def dismiss_modals_if_present(self) -> None:
        """Idempotently close any visible modal overlay without failing if already closed."""
        self.dismiss_any_alert()
        for modal_id in self.MODAL_IDS:
            try:
                el = self.driver.find_element(By.ID, modal_id)
                if el.is_displayed():
                    self.driver.execute_script("arguments[0].style.display = 'none';", el)
            except Exception:
                continue

    def capture_step_screenshot(self, name: str) -> Path:
        """Save a stepwise verification screenshot under `SCREENSHOTS_DIR`."""
        self.dismiss_any_alert()
        SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        path = SCREENSHOTS_DIR / f"{name}.png"
        self.driver.save_screenshot(str(path))
        return path

    def collect_severe_console_logs(self) -> list[dict[str, Any]]:
        """Return any SEVERE browser console error logs."""
        try:
            logs = self.driver.get_log("browser")
        except Exception:
            return []
        severe = []
        for entry in logs:
            if entry.get("level") == "SEVERE":
                msg = entry.get("message", "")
                if "favicon.ico" in msg:
                    continue
                severe.append(entry)
        return severe

    def check_dom_integrity(self) -> dict[str, Any]:
        """Inspect live DOM for unresolved template placeholders or duplicate element IDs."""
        self.dismiss_any_alert()
        return self.driver.execute_script(
            """
            const bodyText = document.body ? document.body.innerText : '';
            const hasUnresolvedTemplate = /\\$\\{[^}]+\\}|\\{\\{[^}]+\\}\\}/.test(bodyText);
            const allIds = Array.from(document.querySelectorAll('[id]')).map(el => el.id).filter(Boolean);
            const seen = new Set();
            const duplicateIds = [];
            for (const id of allIds) {
                if (seen.has(id)) duplicateIds.push(id);
                seen.add(id);
            }
            return {
                hasUnresolvedTemplate,
                duplicateIds
            };
            """
        )

    def cleanup_created_resources(self, created_resources: list[tuple[str, str]]) -> None:
        """Delete only the test-created resources recorded in `created_resources`."""
        if not created_resources:
            return
        self.dismiss_any_alert()
        payload = json.dumps(created_resources)
        self.driver.execute_script(
            """
            const resources = JSON.parse(arguments[0]);
            const removeFromKey = (storageKey, predicate) => {
                const raw = localStorage.getItem(storageKey);
                if (!raw) return;
                try {
                    const arr = JSON.parse(raw);
                    if (Array.isArray(arr)) {
                        const filtered = arr.filter(item => !predicate(item));
                        localStorage.setItem(storageKey, JSON.stringify(filtered));
                    }
                } catch (e) {}
            };

            for (const [kind, identifier] of resources) {
                if (kind === 'customer') {
                    removeFromKey('bookkeeping_customers', c => c.name === identifier);
                } else if (kind === 'supplier') {
                    removeFromKey('bookkeeping_suppliers', s => s.name === identifier);
                } else if (kind === 'inventory') {
                    removeFromKey('bookkeeping_inventory', i => i.name === identifier);
                    removeFromKey('bookkeeping_stock_ledger', l => l.productName === identifier);
                } else if (kind === 'employee') {
                    removeFromKey('bookkeeping_employees', e => e.name === identifier);
                } else if (kind === 'cheque') {
                    removeFromKey('bookkeeping_cheques', c => c.chequeNumber === identifier);
                } else if (kind === 'coa') {
                    removeFromKey('bookkeeping_coa', a => a.code === identifier);
                    removeFromKey('bookkeeping_custom_accounts', a => a.code === identifier);
                } else if (kind === 'ledger') {
                    removeFromKey('bookkeeping_history_v2', h =>
                        h.invoiceNum === identifier ||
                        h.entityName === identifier ||
                        h.description === identifier ||
                        (h.description && h.description.includes(identifier))
                    );
                } else if (kind === 'asset') {
                    removeFromKey('bookkeeping_assets', a => a.description === identifier);
                } else if (kind === 'accrual') {
                    removeFromKey('bookkeeping_accruals', a => a.description === identifier);
                } else if (kind === 'bank_rule') {
                    removeFromKey('bookkeeping_bank_rules', r => r.name === identifier);
                } else if (kind === 'bank_statement') {
                    removeFromKey('bookkeeping_bank_statements', s => s.accountNumber === identifier || s.bankName === identifier);
                } else if (kind === 'quote') {
                    removeFromKey('bookkeeping_quotes', q => q.quoteNum === identifier);
                } else if (kind === 'po') {
                    removeFromKey('bookkeeping_pos', p => p.poNum === identifier);
                } else if (kind === 'recurring') {
                    removeFromKey('bookkeeping_recurring_v2', r => r.name === identifier);
                } else if (kind === 'currency') {
                    removeFromKey('bookkeeping_currencies', c => c.code === identifier);
                } else if (kind === 'payroll') {
                    localStorage.removeItem('payroll_' + identifier);
                } else if (kind === 'closed_date') {
                    localStorage.removeItem('bookkeeping_closed_date');
                } else if (kind === 'budget') {
                    const rawBudgets = localStorage.getItem('bookkeeping_budgets');
                    if (rawBudgets) {
                        try {
                            const budgetsObj = JSON.parse(rawBudgets);
                            if (budgetsObj && typeof budgetsObj === 'object') {
                                delete budgetsObj[identifier];
                                localStorage.setItem('bookkeeping_budgets', JSON.stringify(budgetsObj));
                            }
                        } catch (e) {}
                    }
                } else if (kind === 'settings') {
                    localStorage.removeItem('bookkeeping_settings');
                    localStorage.removeItem('erp_settings');
                } else if (kind === 'bank_feeds') {
                    localStorage.removeItem('bookkeeping_bank_feeds');
                } else if (kind === 'lang') {
                    if (window.LumenI18n) window.LumenI18n.setLang(identifier || 'en');
                    else localStorage.setItem('lumen_lang', identifier || 'en');
                } else if (kind === 'expense') {
                    removeFromKey('bookkeeping_history_v2', h =>
                        h.expenseId === identifier || h.entityName === identifier
                    );
                } else if (kind === 'fx_backup') {
                    localStorage.removeItem('bookkeeping_history_fx_backup');
                }
            }
            """,
            payload,
        )
