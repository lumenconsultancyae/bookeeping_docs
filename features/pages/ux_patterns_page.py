"""Page Object for cross-cutting UX patterns: paginated tables, inline validation, dialogs, toasts, drawer."""

from __future__ import annotations

import json
from typing import Any

from selenium.webdriver.common.by import By

from features.pages.base_page import BasePage


class UxPatternsPage(BasePage):
    """UI adapter for `ui-tables.js`, `ui-forms.js`, `ui-feedback.js` and `ui-layout.js` behaviour."""

    # --- Test data arrangement (localStorage seeding, then reload like a returning user) ---

    def seed_customers(self, names: list[str]) -> None:
        """Append customers to `bookkeeping_customers` and reload the workspace."""
        self.driver.execute_script(
            """
            const list = JSON.parse(localStorage.getItem('bookkeeping_customers') || '[]');
            JSON.parse(arguments[0]).forEach((name, i) => list.push({ name, trn: String(100000000000000 + i),
                address: 'Business Bay, Dubai', email: '', phone: '', terms: 30 }));
            localStorage.setItem('bookkeeping_customers', JSON.stringify(list));
            """,
            json.dumps(names),
        )
        self.open_application()

    def seed_journal_entries(self, descriptions: list[str]) -> None:
        """Prepend journal entries to `bookkeeping_history_v2` and reload the workspace."""
        self.driver.execute_script(
            """
            const history = JSON.parse(localStorage.getItem('bookkeeping_history_v2') || '[]');
            JSON.parse(arguments[0]).forEach((description, i) => history.unshift({
                id: 'ux-seed-' + Date.now() + '-' + i, type: 'journal', date: '2026-10-' + String(1 + (i % 27)).padStart(2, '0'),
                entityName: 'UX Seed', description, drAcc: '6000 Rent Expense', crAcc: '1000 Cash',
                subtotal: 100 + i, discount: 0, tax: 0, total: 100 + i, status: 'posted' }));
            localStorage.setItem('bookkeeping_history_v2', JSON.stringify(history));
            """,
            json.dumps(descriptions),
        )
        self.open_application()

    # --- Paginated tables ---

    def table_snapshot(self, tbody_id: str) -> dict[str, Any]:
        """Return visible row texts, pager summary and current page for a paginated tbody."""
        return self.driver.execute_script(
            """
            const tb = document.getElementById(arguments[0]);
            const card = tb.closest('.card') || document;
            const rows = Array.from(tb.rows).filter((r) => getComputedStyle(r).display !== 'none');
            const pager = card.querySelector('.table-pager');
            return {
                rows: rows.map((r) => r.textContent.replace(/\\s+/g, ' ').trim()),
                highlighted: Array.from(tb.querySelectorAll('tr.row-highlight')).map((r) => r.textContent),
                summary: pager ? pager.querySelector('.table-pager__summary').textContent : '',
                pagerVisible: Boolean(pager && !pager.hidden),
                current: pager && pager.querySelector('[aria-current="page"]') ? pager.querySelector('[aria-current="page"]').textContent : '',
            };
            """,
            tbody_id,
        )

    def go_to_table_page(self, tbody_id: str, page: str) -> None:
        self.driver.execute_script(
            "const card = document.getElementById(arguments[0]).closest('.card');"
            "card.querySelector('.table-pager [aria-label=\"Page ' + arguments[1] + '\"]').click();",
            tbody_id,
            page,
        )

    def search_table(self, tbody_id: str, query: str) -> None:
        card = self.driver.find_element(By.ID, tbody_id).find_element(By.XPATH, "./ancestor::div[contains(@class,'card')][1]")
        box = card.find_element(By.CSS_SELECTOR, ".table-search input")
        box.clear()
        box.send_keys(query)

    def workspace_scroll_ratio(self) -> float:
        return float(self.driver.execute_script(
            "const c = document.querySelector('.dashboard-content'); return c.scrollHeight / c.clientHeight;"))

    # --- Inline validation ---

    def submit_customer_form(self, name: str, trn: str) -> None:
        """Fill name/TRN (an empty name clears the field) and click the form's submit button."""
        if name:
            self.fill_input("dirCustName", name)
        else:
            self.driver.execute_script("document.getElementById('dirCustName').value = '';")
        self.fill_input("dirCustTrn", trn)
        self.driver.execute_script("document.querySelector('#addCustomerForm button[type=\"submit\"]').click();")

    def inline_error(self, field_id: str) -> str:
        return self.wait_until(lambda d: d.execute_script(
            "const f = document.getElementById(arguments[0]); const e = document.getElementById(arguments[0] + '-error');"
            "return f.getAttribute('aria-invalid') === 'true' && e && !e.hidden ? e.textContent : false;", field_id))

    # --- Dialogs & toasts ---

    def click_row_action(self, tbody_id: str, row_text: str, action: str) -> None:
        self.driver.execute_script(
            """
            const [id, text, action] = arguments;
            const row = Array.from(document.getElementById(id).rows).find((r) => r.textContent.includes(text));
            Array.from(row.querySelectorAll('button')).find((b) => b.textContent.trim() === action).click();
            """,
            tbody_id, row_text, action,
        )

    def open_dialog(self) -> dict[str, Any]:
        return self.wait_until(lambda d: d.execute_script(
            """
            const dlg = document.querySelector('.lumen-dialog');
            if (!dlg) return false;
            return { title: dlg.querySelector('.lumen-dialog__title').textContent,
                     message: (dlg.querySelector('.lumen-dialog__message') || {}).textContent || '',
                     danger: dlg.classList.contains('lumen-dialog--danger'), role: dlg.getAttribute('role') };
            """))

    def answer_dialog(self, confirm: bool) -> None:
        self.driver.execute_script(
            "document.querySelector('.lumen-dialog [data-dialog-action=\"' + arguments[0] + '\"]').click();",
            "confirm" if confirm else "cancel",
        )
        self.wait_until(lambda d: not d.find_elements(By.CSS_SELECTOR, ".lumen-dialog"))

    def latest_toast(self) -> dict[str, str]:
        return self.wait_until(lambda d: d.execute_script(
            """
            const toasts = document.querySelectorAll('#lumenToastRegion .lumen-toast:not([data-leaving])');
            const t = toasts[toasts.length - 1];
            return t ? { type: t.className.match(/lumen-toast--(\\w+)/)[1], text: t.textContent } : false;
            """))

    def visible_toast_count(self) -> int:
        return int(self.driver.execute_script(
            "return document.querySelectorAll('#lumenToastRegion .lumen-toast:not([data-leaving])').length;"))

    # --- Responsive drawer ---

    def drawer_state(self) -> dict[str, Any]:
        return self.driver.execute_script(
            """
            const sb = document.querySelector('.sidebar').getBoundingClientRect();
            const backdrop = document.querySelector('.sidebar-backdrop');
            return { open: document.body.classList.contains('sidebar-open'), sidebarRight: sb.right, sidebarLeft: sb.left,
                     expanded: document.getElementById('btnSidebarToggle').getAttribute('aria-expanded'),
                     backdrop: Boolean(backdrop && getComputedStyle(backdrop).display !== 'none') };
            """)
