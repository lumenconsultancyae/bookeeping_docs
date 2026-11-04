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
        self.driver.execute_script(
            "if (typeof window.renderTrialBalance === 'function') window.renderTrialBalance();"
        )
        return self.get_text_by_id("incomeStatementContainer")

    def get_balance_sheet_text(self) -> str:
        """Render and return the text of `#balanceSheetContainer`."""
        self.driver.execute_script(
            "if (typeof window.renderTrialBalance === 'function') window.renderTrialBalance();"
        )
        return self.get_text_by_id("balanceSheetContainer")

    def get_cashflow_statement_text(self) -> str:
        """Render and return the text of `#cashflowContainer`."""
        self.driver.execute_script(
            "if (typeof window.renderTrialBalance === 'function') window.renderTrialBalance();"
        )
        return self.get_text_by_id("cashflowContainer")

    # --- UAE VAT 201 Report (`#view-tax`) ---

    def get_vat_return_summary(self) -> dict[str, str]:
        """Render the VAT report and return Box 1, Box 9, Net VAT, and Box 14 values."""
        self.driver.execute_script(
            "if (typeof window.renderTrialBalance === 'function') window.renderTrialBalance();"
        )
        return {
            "output_vat": self.get_text_by_id("vatOutputSummary"),
            "input_vat": self.get_text_by_id("vatInputSummary"),
            "net_vat": self.get_text_by_id("vatNetSummary"),
            "box1": self.get_text_by_id("vatBox1"),
            "box9": self.get_text_by_id("vatBox9"),
            "box14": self.get_text_by_id("vatBox14"),
        }

    def export_fta_audit_file(self) -> dict[str, str]:
        """Click `#btnExportFaf` in `#view-tax` and return the exported FTA Audit File metadata and CSV."""
        self.click_id("btnExportFaf")
        result = self.driver.execute_script(
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
        self.driver.execute_script(
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
        self.driver.execute_script(
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
        self.driver.execute_script(
            "if (typeof window.renderCashflowForecast === 'function') window.renderCashflowForecast();"
        )
        return self.get_text_by_id("cashflowForecastContainer")

    # --- System Audit Log (`#view-audit`) ---

    def get_audit_log_text(self) -> str:
        """Render and return the text of `#auditLogBody`."""
        self.driver.execute_script(
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
        self.driver.execute_script(
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
