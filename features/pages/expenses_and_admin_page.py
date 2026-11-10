"""Page Object for Direct Expenses (`#view-expense`), Deferred Revenue (`2150`), Legal Modals, Plan Gating, and Super-Admin (`/admin`)."""

from __future__ import annotations

from features.pages.base_page import BasePage


class ExpensesAndAdminPage(BasePage):
    """UI adapter for Direct Spend (`#view-expense`), Welcome Legal Modals, Plan Gating, and `/admin` Console."""

    # --- Direct Expenses (`#view-expense`) ---

    def record_direct_expense(
        self,
        *,
        expense_date: str,
        payee: str,
        description: str,
        account: str,
        paid_from: str,
        emirate: str,
        vat_treatment: str,
        amount_excl_vat: str,
        apply_vat: bool = True,
    ) -> str:
        """Populate the Direct Expense form (`#view-expense`) and click `#expSaveBtn`."""
        exp_num = self.get_value_by_id("expNumber")
        self.fill_input("expDate", expense_date)
        self.fill_input("expPayee", payee)
        self.fill_input("expDesc", description)
        self.select_by_value_or_text("expAccount", account)
        self.select_by_value_or_text("expPaidFrom", paid_from)
        self.select_by_value_or_text("expEmirate", emirate)
        self.select_by_value_or_text("expVatTreatment", vat_treatment)
        self.fill_input("expAmount", amount_excl_vat)

        self.evaluate_script(
            """
            const cb = document.getElementById('expApplyVat');
            if (cb) {
                cb.checked = Boolean(arguments[0]);
                cb.dispatchEvent(new Event('change', {bubbles: true}));
            }
            """,
            apply_vat,
        )
        self.click_id("expSaveBtn")
        return exp_num

    def get_expense_history_summary(self) -> dict[str, str]:
        """Return the Expense History table text, total amount, and count badge."""
        return {
            "body": self.get_text_by_id("expListBody"),
            "total": self.get_text_by_id("expListTotal"),
            "count": self.get_text_by_id("expCount"),
        }

    def edit_direct_expense_amount(self, expense_id: str, new_amount: str, apply_vat: bool = True) -> None:
        """Invoke `window.editExpenseById(expense_id)`, update `#expAmount`, and save."""
        self.evaluate_script(
            "if (typeof window.editExpenseById === 'function') window.editExpenseById(arguments[0]);",
            expense_id,
        )
        self.fill_input("expAmount", new_amount)
        self.evaluate_script(
            """
            const cb = document.getElementById('expApplyVat');
            if (cb) {
                cb.checked = Boolean(arguments[0]);
                cb.dispatchEvent(new Event('change', {bubbles: true}));
            }
            """,
            apply_vat,
        )
        self.click_id("expSaveBtn")

    # --- Deferred Revenue (`2150`) Customer Invoice ---

    def enable_customer_invoice_deferred_revenue(self, life_months: str = "6") -> None:
        """Enable `#custIsPrepaid` on the Customer Sales Invoice form and set `#custPrepaidMonths`."""
        self.evaluate_script(
            """
            const cb = document.getElementById('custIsPrepaid');
            if (cb) {
                cb.checked = true;
                cb.dispatchEvent(new Event('change', {bubbles: true}));
            }
            const months = document.getElementById('custPrepaidMonths');
            if (months) {
                months.value = arguments[0];
                months.dispatchEvent(new Event('input', {bubbles: true}));
            }
            """,
            str(life_months),
        )

    def set_customer_invoice_emirate(self, emirate: str) -> None:
        """Select `#custEmirate` on the Customer Sales Invoice form."""
        self.select_by_value_or_text("custEmirate", emirate)

    # --- Welcome Legal Modals (`/welcome`) ---

    def open_welcome_legal_modal(self, legal_key: str) -> dict[str, str]:
        """Click `[data-legal="<legal_key>"]` on `/welcome` and return modal title and body text."""
        def _open(p) -> bool:
            p.locator(f'[data-legal="{legal_key}"]').evaluate("el => el.click()")
            return p.locator("#legalModal").is_visible()

        self.wait_until(_open)
        title = self.get_text_by_id("legalModalTitle")
        body = self.get_text_by_id("legalModalBody")
        self.click_id("btnLegalClose")
        return {"title": title, "body": body}

    # --- Plan Gating & Customer Upgrade Request ---

    def is_sidebar_view_locked(self, target_view_id: str) -> bool:
        """Return True if `.nav-item[data-target="<target_view_id>"]` has `.is-locked` and `.lock-badge`."""
        return bool(
            self.evaluate_script(
                """
                const item = document.querySelector('.nav-item[data-target="' + arguments[0] + '"]');
                return Boolean(item && item.classList.contains('is-locked') && item.querySelector('.lock-badge'));
                """,
                target_view_id,
            )
        )

    def request_customer_plan_upgrade_in_settings(self) -> str:
        """Click `#btnRequestPlanUpgrade` in `#view-settings`, confirm the modal, and return `#planSettingsCard` text."""
        self.click_id("btnRequestPlanUpgrade")
        self.wait_until(
            lambda p: p.locator('.lumen-dialog-backdrop [data-dialog-action="confirm"]').count() > 0
        )
        self.evaluate_script(
            """
            const okBtn = document.querySelector('.lumen-dialog-backdrop [data-dialog-action="confirm"]');
            if (okBtn) okBtn.click();
            """
        )
        self.wait_until(
            lambda p: "Upgrade requested:" in p.locator("#planSettingsCard").inner_text()
        )
        return self.get_text_by_id("planSettingsCard")

    # --- Super-Admin Console (`/admin`) ---

    def open_and_sign_in_to_admin_console(self, email: str, password: str) -> None:
        """Simulate a fresh browser session on another computer, navigate to `/admin`, sign in, and wait for `#adminConsoleSection`."""
        self.evaluate_script(
            "try { window.localStorage.clear(); window.sessionStorage.clear(); } catch (_) {}"
        )
        self.page.goto(f"{self.base_url}/admin", wait_until="domcontentloaded")
        self.wait_for_document_ready()
        login_visible = self.evaluate_script(
            """
            const sec = document.getElementById('adminLoginSection');
            return Boolean(sec && !sec.hidden);
            """
        )
        if login_visible:
            self.fill_input("adminLoginEmail", email)
            self.fill_input("adminLoginPassword", password)
            self.click_id("btnAdminLoginSubmit")
        self.wait_until(
            lambda _p: self.evaluate_script(
                """
                const sec = document.getElementById('adminConsoleSection');
                return Boolean(sec && !sec.hidden);
                """
            )
        )
        self.collect_severe_console_logs()

    def open_books_for_company_in_admin(self, company_name: str) -> None:
        """Click `[data-open-advisor]` (`Open Books`) for `company_name` in `/admin` and wait for `.app-layout`."""
        self.evaluate_script(
            """
            const rows = Array.from(document.querySelectorAll('#adminAccountsBody tr'));
            const row = rows.find(r => r.innerText.includes(arguments[0]));
            if (row) {
                const btn = row.querySelector('[data-open-advisor]');
                if (btn) btn.click();
            }
            """,
            company_name,
        )
        self.wait_until(
            lambda _p: self.evaluate_script(
                "return Boolean(document.querySelector('.app-layout') && document.readyState !== 'loading');"
            )
        )
        self.collect_severe_console_logs()

    def get_physical_local_storage_keys(self) -> list[str]:
        """Return the keys actually stored in physical `window.localStorage`."""
        return self.evaluate_script("return Object.keys(window.localStorage);")

    def get_admin_console_summary(self) -> dict[str, str]:
        """Return MRR KPI and tenant table text from `/admin`."""
        return {
            "mrr": self.get_text_by_id("adminKpiMrr"),
            "accounts": self.get_text_by_id("adminKpiAccounts"),
            "table": self.get_text_by_id("adminAccountsBody"),
        }

    def toggle_auto_renew_in_settings(self) -> str:
        """Click `#btnToggleAutoRenew` in `#planSettingsCard` and return the updated `#planSettingsCard` text."""
        self.click_id("btnToggleAutoRenew")
        return self.get_text_by_id("planSettingsCard")

    def trigger_admin_trial_reminder_and_auto_deduct(self, company_name: str) -> str:
        """Click `[data-send-reminder]` and `[data-auto-charge]` for `company_name` in `/admin` and return updated table text."""
        self.evaluate_script(
            """
            const rows = Array.from(document.querySelectorAll('#adminAccountsBody tr'));
            const row = rows.find(r => r.innerText.includes(arguments[0]));
            if (row) {
                const remBtn = row.querySelector('[data-send-reminder]');
                if (remBtn) remBtn.click();
            }
            """,
            company_name,
        )
        self.evaluate_script(
            """
            const rows = Array.from(document.querySelectorAll('#adminAccountsBody tr'));
            const row = rows.find(r => r.innerText.includes(arguments[0]));
            if (row) {
                const chgBtn = row.querySelector('[data-auto-charge]');
                if (chgBtn) chgBtn.click();
            }
            """,
            company_name,
        )
        self.wait_until(
            lambda p: "Charged AED" in p.locator("#adminAccountsBody").inner_text()
        )
        return self.get_text_by_id("adminAccountsBody")

    def approve_upgrade_request_in_admin(self, company_name: str) -> str:
        """Click the `[data-approve-req]` button for `company_name` in `/admin` and return updated row text."""
        self.evaluate_script(
            """
            const rows = Array.from(document.querySelectorAll('#adminAccountsBody tr'));
            const row = rows.find(r => r.innerText.includes(arguments[0]));
            if (row) {
                const btn = row.querySelector('[data-approve-req]');
                if (btn) btn.click();
            }
            """,
            company_name,
        )
        return self.get_text_by_id("adminAccountsBody")

    def delete_company_in_admin(self, company_name: str) -> str:
        """Click `[data-delete-account]` twice for `company_name` in `/admin` and return updated table text."""
        for _ in range(2):
            self.evaluate_script(
                """
                const rows = Array.from(document.querySelectorAll('#adminAccountsBody tr'));
                const row = rows.find(r => r.innerText.includes(arguments[0]));
                if (row) {
                    const btn = row.querySelector('[data-delete-account]');
                    if (btn) btn.click();
                }
                """,
                company_name,
            )
        self.wait_until(
            lambda p: company_name not in p.locator("#adminAccountsBody").inner_text()
        )
        return self.get_text_by_id("adminAccountsBody")
