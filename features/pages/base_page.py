"""Base Page Object encapsulating atomic explicit waits, navigation, alerts, and teardown via Playwright."""

from __future__ import annotations

import json
from pathlib import Path
import threading
import time
from typing import Any, Callable
try:
    from playwright.sync_api import Error as PlaywrightError, Page, TimeoutError as PlaywrightTimeoutError
except ModuleNotFoundError:  # pragma: no cover - fallback when running via Selenium adapter
    PlaywrightError = Exception  # type: ignore[misc,assignment]
    PlaywrightTimeoutError = TimeoutError  # type: ignore[misc,assignment]
    Page = Any  # type: ignore[misc,assignment]

from features.config import DEFAULT_TIMEOUT_SECONDS, POLL_FREQUENCY_SECONDS, SCREENSHOTS_DIR


class BasePage:
    """Playwright base adapter with retry-aware wait predicates and teardown helpers."""

    MODAL_IDS = (
        "duplicateInvoiceModal", "invoiceModal", "editLedgerModal", "editAssetModal",
        "editAccrualModal", "matchPaymentModal", "matchInvoiceToPaymentModal",
        "expenseBreakdownModal", "accrualScheduleModal", "bankLedgerModal",
        "timesheetModal", "coaModal", "addEmployeeModal", "bankRuleModal",
    )

    VIEW_TARGET_MAP = {
        "Dashboard": "view-dashboard", "Banking": "view-bank", "Cheque Registry": "view-cheques",
        "Quotes & Estimates": "view-quotes", "Sales Invoices": "view-customer",
        "Purchase Orders": "view-po", "Supplier Bills": "view-supplier", "Expenses": "view-expense",
        "Chart of Accounts": "view-coa", "Journal Entries": "view-journal",
        "General Ledger": "view-ledger", "SOA": "view-statement",
        "Statement of Account": "view-statement", "Accruals": "view-accrual",
        "Recurring Transactions": "view-recurring", "Customers": "view-customer-list",
        "Suppliers": "view-supplier-list", "Inventory Directory": "view-inventory",
        "Stock Ledger": "view-stock-ledger", "Assets Directory": "view-assets",
        "Employee details": "view-employee-list", "Timesheet & WPS": "view-timesheet",
        "VAT": "view-tax", "Tax Reports": "view-tax", "Corporate Tax": "view-corp-tax",
        "Budgeting vs. Actuals": "view-budgeting", "Cash Flow Forecast": "view-cashflow-forecast",
        "Profit & Loss": "view-income-statement", "Balance Sheet": "view-balance-sheet",
        "Cash Flow": "view-cashflow", "Statement of Equity": "view-equity-statement",
        "Trial Balance": "view-trial", "Audit Log": "view-audit", "Settings": "view-settings",
    }

    def __init__(self, page: Page, base_url: str) -> None:
        self.page, self.base_url, self._audit_snapshot = page, base_url, None

    def evaluate_script(self, script: str, *args: Any) -> Any:
        """Execute a JavaScript function body in the active Playwright page context."""
        return self.page.evaluate(
            "([__body, __args]) => (new Function(__body))(...__args)",
            [script, list(args)],
        )

    def wait_until(
        self,
        predicate: Callable[[Page], Any],
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        poll_frequency: float = POLL_FREQUENCY_SECONDS,
    ) -> Any:
        """Execute an atomic predicate inside a retry-aware Playwright wait loop."""
        deadline = time.monotonic() + timeout
        last_exc: Exception | None = None
        while True:
            try:
                value = predicate(self.page)
                if value:
                    return value
            except (PlaywrightError, Exception) as exc:
                last_exc = exc
            if time.monotonic() >= deadline:
                msg = f"Timed out after {timeout}s waiting for predicate"
                if last_exc is not None:
                    raise PlaywrightTimeoutError(f"{msg}: {last_exc}") from last_exc
                raise PlaywrightTimeoutError(msg)
            threading.Event().wait(poll_frequency)

    def _is_document_ready(self) -> bool:
        """Return True when the active page and its async module manifest have finished booting."""
        return bool(
            self.evaluate_script(
                """
                if (window.__LUMEN_AUTH_REDIRECTING__) return false;
                if (document.readyState !== 'complete') return false;
                if (!window.LumenProfiles) return false;
                if (document.getElementById('root')) {
                    if (
                        !window.updateDashboard ||
                        !document.getElementById('btnTopbarSignOut') ||
                        !window.LumenLayout
                    ) {
                        return false;
                    }
                    if (!window.__LUMEN_BOOT_SETTLED_AT__) {
                        window.__LUMEN_BOOT_SETTLED_AT__ = performance.now();
                        return false;
                    }
                    return (performance.now() - window.__LUMEN_BOOT_SETTLED_AT__) >= 80;
                }
                return true;
                """
            )
        )

    def wait_for_document_ready(self) -> None:
        """Wait until document.readyState === 'complete' and async manifest boot has finished."""
        self.wait_until(lambda _p: self._is_document_ready())

    def open_application(self) -> None:
        """Navigate to the application root and wait for initialization."""
        self.page.goto(self.base_url, wait_until="load")
        self.wait_for_document_ready()
        if self.evaluate_script(
            """
            if (!window.LumenProfiles) return true;
            if (!window.LumenProfiles.isAuthenticated() || !window.LumenProfiles.isOwner()) return true;
            if (window.LumenProfiles.isImpersonating && window.LumenProfiles.isImpersonating()) return true;
            return false;
            """
        ):
            self.evaluate_script(
                "window.LumenProfiles.signIn(window.LumenProfiles.OWNER_ACCOUNT);"
            )
            self.page.goto(self.base_url, wait_until="load")
            self.wait_for_document_ready()
        self.wait_until(
            lambda p: p.locator("#view-dashboard").is_visible()
            and self._is_document_ready()
        )
        if self._audit_snapshot is None:
            self._audit_snapshot = self.evaluate_script("return localStorage.getItem('bookkeeping_audit_log') || '[]';")
        self.collect_severe_console_logs()

    def _check_welcome_ready(self, p: Page) -> bool:
        url = p.url
        vis = p.locator("#btnOpenSignIn").is_visible()
        ready = self.evaluate_script("return document.readyState;")
        if "/welcome" in url and vis and ready in ("interactive", "complete"):
            return True
        raise AssertionError(
            f"url={url!r}, btnOpenSignIn={vis}, readyState={ready!r}, topbarUser={p.locator('#topbarUserActions').is_visible()}"
        )

    def open_unauthenticated_root(self) -> str:
        """Sign out any active session, open `/`, and wait for redirect to `/welcome`."""
        self.page.goto(f"{self.base_url}/welcome", wait_until="load")
        self.wait_for_document_ready()
        self.evaluate_script(
            "if (window.LumenProfiles) window.LumenProfiles.signOut();"
        )
        self.page.goto(self.base_url, wait_until="load")
        self.wait_until(self._check_welcome_ready)
        self.collect_severe_console_logs()
        return self.page.url

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
        self.wait_until(lambda p: p.locator("#setupModal").is_visible())
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
            lambda p: p.locator("#view-dashboard").is_visible()
            and self._is_document_ready()
        )
        self.collect_severe_console_logs()

    def sign_out_from_topbar(self) -> str:
        """Click `#btnTopbarSignOut` and wait for redirect to `/welcome`."""
        self.wait_for_document_ready()
        self.click_id("btnTopbarSignOut")
        self.wait_until(self._check_welcome_ready)
        self.collect_severe_console_logs()
        return self.page.url

    def submit_sign_in_on_welcome(self, email: str, password: str) -> None:
        """Open the Sign-in modal on `/welcome` if hidden and submit credentials."""
        def _ensure_modal_open(p: Page) -> bool:
            modal = p.locator("#signInModal")
            if not modal.is_visible():
                p.locator("#btnOpenSignIn").evaluate("el => el.click()")
            return modal.is_visible()

        self.wait_until(_ensure_modal_open)
        self.fill_input("signInEmail", email)
        self.fill_input("signInPassword", password)
        self.click_id("btnSignInSubmit")

    def get_sign_in_error_text(self) -> str:
        """Return the validation/authentication error message inside `#signInError`."""
        return self.wait_until(
            lambda p: p.locator("#signInError").inner_text().strip()
        )

    def get_topbar_user_name(self) -> str:
        """Return the displayed `.user-profile .user-name` text."""
        def _read_name(p: Page) -> str:
            if not self._is_document_ready():
                return ""
            return p.locator(".user-profile .user-name").inner_text().strip()

        return self.wait_until(_read_name)

    def navigate_to_view(self, view_label: str) -> str:
        """Click the sidebar navigation link for `view_label` and wait for its view container."""
        target_id = self.VIEW_TARGET_MAP.get(view_label, view_label)

        def _click_and_verify(p: Page) -> bool:
            p.locator(f'.nav-item[data-target="{target_id}"]').first.evaluate("el => el.click()")
            return p.locator(f"#{target_id}").is_visible()

        self.wait_until(_click_and_verify)
        return target_id

    def get_active_page_title(self) -> str:
        """Return the text of `#pageTitle`."""
        def _read_title(p: Page) -> str:
            if not self._is_document_ready():
                return ""
            return p.locator("#pageTitle").inner_text().strip()

        return self.wait_until(_read_title)

    def toggle_language(self) -> None:
        """Click the topbar language switcher button (`#btnLangToggle`)."""
        self.click_id("btnLangToggle")

    def get_document_lang_and_dir(self) -> tuple[str, str]:
        """Return `(lang, dir)` attributes of `document.documentElement`."""
        res = self.evaluate_script(
            "return [document.documentElement.lang || '', document.documentElement.dir || ''];"
        )
        return str(res[0]), str(res[1])

    def get_welcome_hero_heading(self) -> str:
        """Return the main hero `<h1>` text on `/welcome`."""
        return self.wait_until(
            lambda p: p.locator("main .hero h1").inner_text().strip()
        )

    def get_welcome_pricing_plans(self) -> list[dict[str, str]]:
        """Return the rendered plan cards (`title`, `amount`, `promo`) inside `#plans` on `/welcome`."""
        self.wait_until(lambda p: p.locator("#plans .plan").count() > 0)
        return self.evaluate_script(
            """
            const cards = Array.from(document.querySelectorAll('#plans .plan'));
            return cards.map(card => ({
                title: (card.querySelector('h2') ? card.querySelector('h2').textContent : '').trim(),
                amount: (card.querySelector('.plan-price .amount') ? card.querySelector('.plan-price .amount').textContent : '').trim(),
                promo: (card.querySelector('.plan-promo-pill') ? card.querySelector('.plan-promo-pill').textContent : '').trim(),
            }));
            """
        )

    def is_view_displayed(self, view_id: str) -> bool:
        """Return True when `#<view_id>` is visible and document boot is complete."""
        return bool(
            self.wait_until(
                lambda p: p.locator(f"#{view_id}").is_visible()
                and self._is_document_ready()
            )
        )

    def fill_input(self, element_id: str, value: str) -> None:
        """Clear and populate an input element by ID."""
        def _fill(p: Page) -> bool:
            loc = p.locator(f"#{element_id}")
            if loc.count() == 0:
                return False
            loc.evaluate(
                """(el, val) => {
                    el.removeAttribute('list');
                    el.value = val;
                    el.dispatchEvent(new Event('input', {bubbles: true}));
                    el.dispatchEvent(new Event('change', {bubbles: true}));
                }""",
                str(value),
            )
            return True

        self.wait_until(_fill)

    def select_by_value_or_text(self, element_id: str, option_text_or_value: str) -> None:
        """Select a `<select>` option by visible text or value attribute."""
        def _select(p: Page) -> bool:
            loc = p.locator(f"#{element_id}")
            if loc.count() == 0:
                return False
            return bool(
                loc.evaluate(
                    """(el, target) => {
                        const opts = Array.from(el.options || []);
                        const match = opts.find(o => o.value === target || (o.textContent || '').trim() === target);
                        if (!match) return false;
                        el.value = match.value;
                        el.dispatchEvent(new Event('change', {bubbles: true}));
                        return true;
                    }""",
                    option_text_or_value,
                )
            )

        self.wait_until(_select)

    def click_id(self, element_id: str) -> None:
        """Click an element by ID using atomic lookup."""
        def _click(p: Page) -> bool:
            loc = p.locator(f"#{element_id}")
            if loc.count() == 0:
                return False
            loc.evaluate("el => el.click()")
            return True

        self.wait_until(_click)

    def get_text_by_id(self, element_id: str) -> str:
        """Return stripped text content of an element by ID."""
        return self.wait_until(
            lambda p: (p.locator(f"#{element_id}").inner_text().strip(),)
        )[0]

    def get_value_by_id(self, element_id: str) -> str:
        """Return the `.value` attribute of an input/select element by ID."""
        return self.wait_until(
            lambda p: (p.locator(f"#{element_id}").input_value().strip(),)
        )[0]

    def post_latest_ledger_entry(self) -> None:
        """Transition the most recently saved ledger entry to 'posted' status via `handleLedgerAction`."""
        self.evaluate_script(
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
                result = self.wait_until(
                    lambda _p: self.evaluate_script(self._FEEDBACK_PROBE_JS, True),
                    timeout=current_timeout,
                    poll_frequency=0.05,
                )
            except PlaywrightTimeoutError:
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
                if not self.evaluate_script(self._FEEDBACK_PROBE_JS, False):
                    break
            except Exception:
                break

    def dismiss_modals_if_present(self) -> None:
        """Idempotently close any visible modal overlay without failing if already closed."""
        self.dismiss_any_alert()
        for modal_id in self.MODAL_IDS:
            try:
                loc = self.page.locator(f"#{modal_id}")
                if loc.count() > 0 and loc.is_visible():
                    loc.evaluate("el => { el.style.display = 'none'; }")
            except Exception:
                continue

    def capture_step_screenshot(self, name: str) -> Path:
        """Save a stepwise verification screenshot under `SCREENSHOTS_DIR`."""
        self.dismiss_any_alert()
        SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        path = SCREENSHOTS_DIR / f"{name}.png"
        self.page.screenshot(path=str(path), timeout=10000)
        return path

    def collect_severe_console_logs(self) -> list[dict[str, Any]]:
        """Return and drain any SEVERE browser console error logs recorded by Playwright listeners."""
        severe_logs = list(getattr(self.page, "_severe_logs", []))
        setattr(self.page, "_severe_logs", [])
        return severe_logs

    def check_dom_integrity(self) -> dict[str, Any]:
        """Inspect live DOM for unresolved template placeholders or duplicate element IDs."""
        self.dismiss_any_alert()
        return self.evaluate_script(
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

    def record_settings_snapshot(self, created_resources: list[tuple[str, str]]) -> None:
        """Capture pre-scenario `bookkeeping_settings` once per scenario so teardown restores it."""
        if not any(kind == "settings" for kind, _ in created_resources):
            raw_settings = self.evaluate_script("return localStorage.getItem('bookkeeping_settings') || '';")
            created_resources.append(("settings", str(raw_settings or "")))

    def isolate_employees_snapshot(self, created_resources: list[tuple[str, str]]) -> None:
        """Snapshot and clear `bookkeeping_employees` once per scenario so payroll runs are deterministic."""
        if not any(kind == "employees_snapshot" for kind, _ in created_resources):
            raw_emps = self.evaluate_script("const r = localStorage.getItem('bookkeeping_employees') || '[]'; localStorage.setItem('bookkeeping_employees', '[]'); return r;")
            created_resources.append(("employees_snapshot", str(raw_emps or "[]")))

    def cleanup_created_resources(self, created_resources: list[tuple[str, str]]) -> None:
        """Delete only the test-created resources recorded in `created_resources`."""
        if not created_resources:
            return
        self.dismiss_any_alert()
        self.evaluate_script(
            "if (window.LumenProfiles && typeof window.LumenProfiles.flushSync === 'function') return window.LumenProfiles.flushSync();"
        )
        items = [*created_resources, ("audit_snapshot", str(self._audit_snapshot))] if self._audit_snapshot is not None else created_resources
        payload = json.dumps(items)
        self.evaluate_script(
            """
            const resources = JSON.parse(arguments[0]);
            const removeFromKey = (storageKey, predicate) => {
                const raw = localStorage.getItem(storageKey);
                if (!raw) return;
                try {
                    const arr = JSON.parse(raw);
                    if (Array.isArray(arr)) localStorage.setItem(storageKey, JSON.stringify(arr.filter(item => !predicate(item))));
                } catch (e) {}
            };

            for (const [kind, identifier] of resources) {
                if (kind === 'customer') removeFromKey('bookkeeping_customers', c => c.name === identifier);
                else if (kind === 'supplier') removeFromKey('bookkeeping_suppliers', s => s.name === identifier);
                else if (kind === 'inventory') {
                    removeFromKey('bookkeeping_inventory', i => i.name === identifier);
                    removeFromKey('bookkeeping_stock_ledger', l => l.productName === identifier);
                } else if (kind === 'employees_snapshot') localStorage.setItem('bookkeeping_employees', (identifier && identifier.trim().startsWith('[')) ? identifier : '[]');
                else if (kind === 'audit_snapshot') localStorage.setItem('bookkeeping_audit_log', (identifier && identifier.trim().startsWith('[')) ? identifier : '[]');
                else if (kind === 'employee') removeFromKey('bookkeeping_employees', e => e.name === identifier);
                else if (kind === 'cheque') removeFromKey('bookkeeping_cheques', c => c.chequeNumber === identifier);
                else if (kind === 'coa') {
                    removeFromKey('bookkeeping_coa', a => a.code === identifier);
                    removeFromKey('bookkeeping_custom_accounts', a => a.code === identifier);
                } else if (kind === 'ledger') {
                    removeFromKey('bookkeeping_history_v2', h =>
                        h.invoiceNum === identifier || h.entityName === identifier ||
                        h.description === identifier || (h.description && h.description.includes(identifier))
                    );
                } else if (kind === 'asset') removeFromKey('bookkeeping_assets', a => a.description === identifier);
                else if (kind === 'accrual') removeFromKey('bookkeeping_accruals', a => a.description === identifier);
                else if (kind === 'bank_rule') removeFromKey('bookkeeping_bank_rules', r => r.name === identifier);
                else if (kind === 'bank_statement') removeFromKey('bookkeeping_bank_statements', s => s.accountNumber === identifier || s.bankName === identifier);
                else if (kind === 'quote') removeFromKey('bookkeeping_quotes', q => q.quoteNum === identifier);
                else if (kind === 'po') removeFromKey('bookkeeping_pos', p => p.poNum === identifier);
                else if (kind === 'recurring') removeFromKey('bookkeeping_recurring_v2', r => r.name === identifier);
                else if (kind === 'currency') removeFromKey('bookkeeping_currencies', c => c.code === identifier);
                else if (kind === 'payroll') localStorage.removeItem('payroll_' + identifier);
                else if (kind === 'closed_date') localStorage.removeItem('bookkeeping_closed_date');
                else if (kind === 'budget') {
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
                    const fallback = JSON.stringify({ companyName: 'Lumen Management Consultancy', companyAddress: 'Business Bay, Dubai, UAE', companyPhone: '+971 56 471 8587', companyType: 'Mainland', smallBusinessRelief: false });
                    localStorage.setItem('bookkeeping_settings', (identifier && identifier.trim().startsWith('{')) ? identifier : fallback);
                    localStorage.removeItem('erp_settings');
                } else if (kind === 'bank_feeds') localStorage.removeItem('bookkeeping_bank_feeds');
                else if (kind === 'lang') {
                    if (window.LumenI18n) window.LumenI18n.setLang(identifier || 'en');
                    else localStorage.setItem('lumen_lang', identifier || 'en');
                } else if (kind === 'expense') removeFromKey('bookkeeping_history_v2', h => h.expenseId === identifier || h.entityName === identifier);
                else if (kind === 'fx_backup') localStorage.removeItem('bookkeeping_history_fx_backup');
            }
            if (window.LumenProfiles && typeof window.LumenProfiles.flushSync === 'function') return window.LumenProfiles.flushSync();
            """,
            payload,
        )
