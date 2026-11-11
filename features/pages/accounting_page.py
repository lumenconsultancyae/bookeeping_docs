"""Page Object for Chart of Accounts, Journal Entries, General Ledger, Accruals, and SOA."""

from __future__ import annotations

from features.pages.base_page import BasePage


class AccountingPage(BasePage):
    """UI adapter for core accounting views (`#view-coa`, `#view-journal`, `#view-ledger`, `#view-accrual`, `#view-statement`)."""

    # --- Chart of Accounts (`#view-coa`) ---

    def add_custom_account(self, code: str, name: str, account_type: str) -> None:
        """Open the Add Account modal, populate fields, and save the custom account."""
        self.click_id("btnAddAccount")
        self.wait_until(lambda p: p.locator("#coaModal").is_visible())
        self.fill_input("coaCode", code)
        self.fill_input("coaName", name)
        self.select_by_value_or_text("coaType", account_type)
        self.click_id("btnSaveCoa")
        self.accept_alert_if_present(timeout=1.5)
        self.wait_until(lambda p: not p.locator("#coaModal").is_visible())

    def get_coa_table_text(self) -> str:
        """Return the visible text of `#coaBody`."""
        return self.get_text_by_id("coaBody")

    # --- Manual Journal Entries (`#view-journal`) ---

    def fill_journal_form(
        self,
        entry_date: str,
        reference: str,
        description: str,
        debit_account: str,
        credit_account: str,
        amount: str,
        vat_treatment: str = "exempt",
        is_ct_add_back: bool = False,
    ) -> None:
        """Populate the manual journal entry form fields."""
        self.fill_input("journalDate", entry_date)
        self.fill_input("journalRef", reference)
        self.fill_input("journalDesc", description)
        self.fill_input("journalDr", debit_account)
        self.fill_input("journalCr", credit_account)
        self.fill_input("journalAmount", amount)

        self.evaluate_script(
            """
            const radios = document.querySelectorAll('input[name="journalVatToggle"]');
            radios.forEach(r => {
                if (r.value === arguments[0]) {
                    r.checked = true;
                    r.dispatchEvent(new Event('change', {bubbles: true}));
                }
            });
            const cb = document.getElementById('journalIsCtAddBack');
            if (cb) {
                cb.checked = Boolean(arguments[1]);
                cb.dispatchEvent(new Event('change', {bubbles: true}));
            }
            """,
            vat_treatment,
            is_ct_add_back,
        )

    def preview_journal_entry(self) -> str:
        """Click Preview Posting and return the preview table text."""
        self.click_id("btnPreviewJournal")
        self.wait_until(
            lambda p: p.locator("#journalPreviewContainer").is_visible()
        )
        return self.get_text_by_id("journalPreviewBody")

    def submit_journal_entry(self) -> str | None:
        """Submit the manual journal entry form, post the entry, and return any alert message."""
        self.evaluate_script(
            "document.getElementById('journalForm').requestSubmit();"
        )
        alert_text = self.accept_alert_if_present(timeout=3.0)
        self.post_latest_ledger_entry()
        return alert_text

    # --- General Ledger (`#view-ledger`) ---

    def get_ledger_table_text(self) -> str:
        """Return the text of `#historyBody`."""
        return self.get_text_by_id("historyBody")

    def lock_ledger_through_date(self, close_date: str) -> str | None:
        """Set `#closeMonthDate`, click `#btnCloseMonth`, and accept the confirmation alert."""
        self.fill_input("closeMonthDate", close_date)
        self.click_id("btnCloseMonth")
        return self.accept_alert_if_present(timeout=3.0)

    def attempt_delete_ledger_entry_by_ref(self, ref_or_desc: str) -> str | None:
        """Attempt to delete a ledger entry matching `ref_or_desc` and return any alert text."""
        entry_id = self.evaluate_script(
            """
            const history = JSON.parse(localStorage.getItem('bookkeeping_history_v2') || '[]');
            const found = history.find(h =>
                h.invoiceNum === arguments[0] ||
                h.description === arguments[0] ||
                (h.description && h.description.includes(arguments[0]))
            );
            return found ? found.id : null;
            """,
            ref_or_desc,
        )
        if entry_id is not None:
            self.evaluate_script(
                """
                const sel = Array.from(document.querySelectorAll('#historyBody select.action-dropdown'))
                    .find(s => !s.disabled && (s.getAttribute('onchange') || '').includes(String(arguments[0])));
                if (sel) { sel.value = 'delete'; sel.dispatchEvent(new Event('change', {bubbles: true})); }
                else window.deleteEntry(arguments[0]);
                """,
                entry_id,
            )
        return self.accept_alert_if_present(timeout=3.0)

    # --- Accruals (`#view-accrual`) ---

    def add_accrual_schedule(
        self,
        start_date: str,
        description: str,
        debit_account: str,
        credit_account: str,
        total_amount: str,
        life_months: str,
        schedule_mode: str = "monthly",
    ) -> None:
        """Populate and submit `#addAccrualForm`."""
        self.fill_input("accrualDate", start_date)
        self.fill_input("accrualDesc", description)
        self.select_by_value_or_text("accrualDrAcc", debit_account)
        self.select_by_value_or_text("accrualCrAcc", credit_account)
        self.select_by_value_or_text("accrualMode", schedule_mode)
        self.fill_input("accrualAmount", total_amount)
        if schedule_mode == "monthly":
            self.fill_input("accrualLife", life_months)
        self.evaluate_script(
            "document.getElementById('addAccrualForm').requestSubmit();"
        )
        self.accept_alert_if_present(timeout=1.5)

    def record_accrual_usage_drawdown(
        self,
        description: str,
        usage_date: str,
        usage_amount: str,
        usage_note: str,
    ) -> None:
        """Open `#recordAccrualUsageModal` for `description`, populate drawdown fields, and save."""
        self.evaluate_script(
            """
            const accruals = JSON.parse(localStorage.getItem('bookkeeping_accruals') || '[]');
            const found = accruals.find(a => a.description === arguments[0]);
            if (found && typeof window.recordAccrualUsage === 'function') {
                window.recordAccrualUsage(found.id);
            }
            """,
            description,
        )
        self.wait_until(
            lambda p: p.locator("#recordAccrualUsageModal").is_visible()
        )
        self.fill_input("recordUsageDate", usage_date)
        self.fill_input("recordUsageAmount", usage_amount)
        self.fill_input("recordUsageNote", usage_note)
        self.click_id("btnSaveAccrualUsage")
        self.accept_alert_if_present(timeout=1.5)
        self.wait_until(
            lambda p: not p.locator("#recordAccrualUsageModal").is_visible()
        )

    def get_calculated_monthly_accrual(self) -> str:
        """Return the auto-calculated `#accrualMonthly` value."""
        return self.get_value_by_id("accrualMonthly")

    def get_accruals_table_text(self) -> str:
        """Return the text of `#accrualsDirectoryBody`."""
        return self.get_text_by_id("accrualsDirectoryBody")

    def open_accrual_schedule_modal(self, description: str) -> str:
        """Open the amortization schedule modal for `description` and return its table text."""
        self.evaluate_script(
            """
            const accruals = JSON.parse(localStorage.getItem('bookkeeping_accruals') || '[]');
            const found = accruals.find(a => a.description === arguments[0]);
            if (found && typeof window.viewAccrualSchedule === 'function') {
                window.viewAccrualSchedule(found.id);
            }
            """,
            description,
        )
        self.wait_until(
            lambda p: p.locator("#accrualScheduleModal").is_visible()
        )
        return self.get_text_by_id("accrualScheduleBody")

    # --- Statement of Account (`#view-statement`) ---

    def load_statement_of_account(self, mode_or_entity: str) -> None:
        """Load the Statement of Account for `'ALL_AR'`, `'ALL_AP'`, or a specific entity name."""
        if mode_or_entity in ("ALL_AR", "ALL_AP"):
            self.evaluate_script(
                "window.loadStatementOfAccount(arguments[0]);", mode_or_entity
            )
        else:
            self.select_by_value_or_text("statementEntitySelect", mode_or_entity)

    def get_statement_kpis(self) -> dict[str, str]:
        """Return the Total Invoice, Total Payment, and Balance KPIs on the SOA view."""
        return {
            "total_invoice": self.get_text_by_id("statementTotalInvoice"),
            "total_payment": self.get_text_by_id("statementTotalPayment"),
            "balance": self.get_text_by_id("statementBalance"),
            "table_text": self.get_text_by_id("statementBody"),
        }
