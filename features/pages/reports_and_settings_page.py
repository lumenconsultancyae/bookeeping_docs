"""Page Object for Financial Statements, UAE VAT/CT Reports, Budgeting, Forecast, Audit Log, and Settings."""

from __future__ import annotations

from features.pages.base_page import BasePage


class ReportsAndSettingsPage(BasePage):
    """UI adapter for reporting, tax, FP&A, audit, and system configuration views."""

    # --- Trial Balance (`#view-trial`) ---

    def get_trial_balance_totals(self) -> dict[str, str]:
        """Set a full-year date range, filter the Trial Balance, and return total debit, credit, and body text."""
        self.fill_input("tbDateFrom", "2026-01-01")
        self.fill_input("tbDateTo", "2026-12-31")
        self.click_id("btnFilterTb")
        return {
            "debit": self.get_text_by_id("tbTotalDebit"),
            "credit": self.get_text_by_id("tbTotalCredit"),
            "body": self.get_text_by_id("tbBody"),
        }

    # --- Financial Statements (`#view-income-statement`, `#view-balance-sheet`, `#view-cashflow`) ---

    def get_income_statement_text(self) -> str:
        """Render and return the text of `#incomeStatementContainer`."""
        self.evaluate_script(
            "if (typeof window.renderTrialBalance === 'function') window.renderTrialBalance();"
        )
        return self.get_text_by_id("incomeStatementContainer")

    def get_balance_sheet_text(self) -> str:
        """Render and return the text of `#balanceSheetContainer`."""
        self.evaluate_script(
            "if (typeof window.renderTrialBalance === 'function') window.renderTrialBalance();"
        )
        return self.get_text_by_id("balanceSheetContainer")

    def get_cashflow_statement_text(self) -> str:
        """Render and return the text of `#cashflowContainer`."""
        self.evaluate_script(
            "if (typeof window.renderTrialBalance === 'function') window.renderTrialBalance();"
        )
        return self.get_text_by_id("cashflowContainer")

    def get_equity_statement_text(self) -> str:
        """Render and return the text of `#equityStatementContainer`."""
        self.evaluate_script(
            "if (typeof window.renderEquityStatement === 'function') window.renderEquityStatement();"
        )
        return self.get_text_by_id("equityStatementContainer")

    # --- UAE VAT 201 Report (`#view-tax`) ---

    def get_vat_return_summary(self) -> dict[str, str]:
        """Render the VAT report and return Box 1, Box 9, Net VAT, and Box 14 values."""
        self.evaluate_script(
            "if (typeof window.renderTrialBalance === 'function') window.renderTrialBalance();"
        )
        return {
            "output_vat": self.get_text_by_id("vatOutputSummary"),
            "input_vat": self.get_text_by_id("vatInputSummary"),
            "net_vat": self.get_text_by_id("vatNetSummary"),
            "box1": self.get_text_by_id("vatBox1"),
            "box1a": self.get_text_by_id("vatBox1a"),
            "box1b": self.get_text_by_id("vatBox1b"),
            "box3": self.get_text_by_id("vatBox3"),
            "box4": self.get_text_by_id("vatBox4"),
            "box5": self.get_text_by_id("vatBox5"),
            "box9": self.get_text_by_id("vatBox9"),
            "box14": self.get_text_by_id("vatBox14"),
        }

    def export_fta_audit_file(self) -> dict[str, str]:
        """Click `#btnExportFaf` in `#view-tax` and return the exported FTA Audit File metadata and CSV."""
        self.click_id("btnExportFaf")
        result = self.evaluate_script(
            """
            const last = window.__lastExportedFAF || {};
            const totals = (last.data && last.data.totals) || {};
            return {
                filename: String(last.filename || ''),
                csv: String(last.csv || ''),
                gl_debit: String(totals.glDebitAED || '0.00'),
                gl_credit: String(totals.glCreditAED || '0.00'),
                banner: (document.getElementById('fafStatusBanner') && document.getElementById('fafStatusBanner').textContent) || ''
            };
            """
        )
        return result or {}

    # --- UAE Corporate Tax Report (`#view-corp-tax`) ---

    def get_corporate_tax_summary(self) -> dict[str, str]:
        """Render the Corporate Tax summary and return Net Profit, Add-Backs, Taxable Income, and Payable."""
        self.evaluate_script(
            "if (typeof window.renderTrialBalance === 'function') window.renderTrialBalance();"
        )
        return {
            "net_profit": self.get_text_by_id("ctNetProfit"),
            "add_backs": self.get_text_by_id("ctAddBacksDisplay"),
            "taxable_income": self.get_text_by_id("ctTaxableIncome"),
            "payable": self.get_text_by_id("ctPayable"),
        }

    # --- Budgeting vs. Actuals (`#view-budgeting`) ---

    def set_budget_for_account_and_save(
        self,
        month_yyyy_mm: str,
        account_name: str,
        budget_amount: str,
    ) -> str | None:
        """Select a budget month, set the budget input for `account_name`, and save budgets."""
        account_code = account_name.split()[0].strip()
        self.fill_input("budgetMonthFilter", month_yyyy_mm)
        self.evaluate_script(
            """
            if (typeof window.renderBudgeting === 'function') window.renderBudgeting();
            const inputs = document.querySelectorAll('#budgetingContainer .budget-input');
            inputs.forEach(inp => {
                if (inp.getAttribute('data-code') === arguments[0]) {
                    inp.value = arguments[1];
                    inp.dispatchEvent(new Event('input', {bubbles: true}));
                }
            });
            if (typeof window.saveCurrentBudgets === 'function') window.saveCurrentBudgets();
            """,
            account_code,
            str(budget_amount),
        )
        return self.accept_alert_if_present(timeout=2.0)

    def get_budgeting_table_text(self) -> str:
        """Return the text of `#budgetingContainer`."""
        return self.get_text_by_id("budgetingContainer")

    # --- Cash Flow Forecast (`#view-cashflow-forecast`) ---

    def get_cashflow_forecast_text(self) -> str:
        """Render and return the 90-day Cash Flow Forecast table text."""
        self.evaluate_script(
            "if (typeof window.renderCashflowForecast === 'function') window.renderCashflowForecast();"
        )
        return self.get_text_by_id("cashflowForecastContainer")

    # --- System Audit Log (`#view-audit`) ---

    def get_audit_log_text(self) -> str:
        """Render and return the text of `#auditLogBody`."""
        self.evaluate_script(
            "if (typeof window.renderAuditLog === 'function') window.renderAuditLog();"
        )
        return self.get_text_by_id("auditLogBody")

    # --- Settings (`#view-settings`) ---

    def save_company_settings(
        self,
        company_name: str,
        company_address: str,
        company_trn: str,
        iban: str,
    ) -> str | None:
        """Populate company letterhead settings and click `#btnSaveCompanySettings`."""
        self.fill_input("companyName", company_name)
        self.fill_input("companyAddress", company_address)
        self.fill_input("companyTrn", company_trn)
        self.fill_input("companyBankIban", iban)
        self.click_id("btnSaveCompanySettings")
        return self.accept_alert_if_present(timeout=2.0)

    def save_tax_settings(
        self,
        company_type: str,
        small_business_relief: bool,
    ) -> str | None:
        """Configure Company Type and Small Business Relief toggle and save tax settings."""
        self.select_by_value_or_text("settingCompanyType", company_type)
        self.evaluate_script(
            """
            const cb = document.getElementById('settingSmallBusinessRelief');
            if (cb) cb.checked = Boolean(arguments[0]);
            """,
            small_business_relief,
        )
        self.click_id("btnSaveTaxSettings")
        return self.accept_alert_if_present(timeout=2.0)

    def add_or_update_currency_rate(self, code: str, rate: str) -> str | None:
        """Add or update a custom currency exchange rate in `#view-settings`."""
        self.fill_input("newCurrencyCode", code)
        self.fill_input("newCurrencyRate", rate)
        self.click_id("btnAddCurrency")
        return self.accept_alert_if_present(timeout=2.0)

    def get_currency_rates_table_text(self) -> str:
        """Return the text of `#currencyRatesBody`."""
        return self.get_text_by_id("currencyRatesBody")

    def seed_unconverted_supplier_bill(self, invoice_num: str, supplier_name: str, total: str) -> None:
        """Insert a legacy supplier bill with no `currency` field into `bookkeeping_history_v2`."""
        self.evaluate_script(
            """
            const raw = localStorage.getItem('bookkeeping_history_v2') || '[]';
            const history = JSON.parse(raw);
            history.unshift({
                id: 'fx_leg_' + arguments[0],
                type: 'supplier',
                status: 'posted',
                date: '2026-09-10',
                invoiceNum: arguments[0],
                entityName: arguments[1],
                subtotal: arguments[2],
                tax: '0.00',
                total: arguments[2],
                drAcc: '6200 Software & SaaS',
                crAcc: '2000 Accounts Payable'
            });
            localStorage.setItem('bookkeeping_history_v2', JSON.stringify(history));
            """,
            invoice_num,
            supplier_name,
            total,
        )

    def convert_legacy_supplier_bill_to_aed(self, invoice_num: str, currency_code: str) -> str:
        """Tick the legacy supplier bill in `#fxFixBody`, convert to AED, and return `#fxFixMessage`."""
        self.evaluate_script(
            """
            const check = document.getElementById('fxFix_fx_leg_' + arguments[0]);
            if (check) check.checked = true;
            const sel = document.getElementById('fxFixCurrency');
            if (sel && arguments[1]) sel.value = arguments[1];
            const convertBtn = document.getElementById('fxFixConvert');
            if (convertBtn) convertBtn.click();
            const yesBtn = document.getElementById('fxFixYes');
            if (yesBtn) yesBtn.click();
            """,
            invoice_num,
            currency_code,
        )
        return self.get_text_by_id("fxFixMessage")

    def undo_legacy_fx_conversion(self) -> str:
        """Click `#fxFixUndo` and return `#fxFixMessage`."""
        self.click_id("fxFixUndo")
        return self.get_text_by_id("fxFixMessage")

