"""Page Object for Employee Directory, Timesheet & WPS Payroll, EOSB, and Fixed Assets."""

from __future__ import annotations

from features.pages.base_page import BasePage


class PayrollAndAssetsPage(BasePage):
    """UI adapter for `#view-employee-list`, `#view-timesheet`, and `#view-assets`."""

    # --- Employee Directory (`#view-employee-list`) ---

    def add_employee(
        self,
        name: str,
        position: str,
        date_hired: str,
        labour_card: str,
        iban: str,
        routing_code: str,
        basic_salary: str,
        housing_allowance: str,
        telephone_allowance: str = "0",
        other_allowance: str = "0",
    ) -> None:
        """Open `#addEmployeeModal`, populate employee details, and submit `#addEmployeeForm`."""
        self.click_id("btnOpenAddEmployee")
        self.wait_until(lambda p: p.locator("#addEmployeeModal").is_visible())
        self.fill_input("dirEmpName", name)
        self.fill_input("dirEmpPosition", position)
        self.fill_input("dirEmpDate", date_hired)
        self.fill_input("dirEmpLabourCard", labour_card)
        self.fill_input("dirEmpIban", iban)
        self.fill_input("dirEmpRouting", routing_code)
        self.fill_input("dirEmpBasic", basic_salary)
        self.fill_input("dirEmpHousing", housing_allowance)
        self.fill_input("dirEmpTelephone", telephone_allowance)
        self.fill_input("dirEmpAllowance", other_allowance)
        self.evaluate_script(
            "document.getElementById('addEmployeeForm').requestSubmit();"
        )
        self.accept_alert_if_present(timeout=1.5)
        self.wait_until(
            lambda p: not p.locator("#addEmployeeModal").is_visible()
        )

    def get_employee_directory_text(self) -> str:
        """Return the text of `#dirEmpBody`."""
        return self.get_text_by_id("dirEmpBody")

    # --- Timesheet, WPS & EOSB (`#view-timesheet`) ---

    def get_eosb_summary_text(self) -> str:
        """Return the text of `#eosbSummaryContainer`."""
        return self.get_text_by_id("eosbSummaryContainer")

    def process_and_save_payroll(
        self,
        pay_period_yyyy_mm: str,
        payment_account: str = "1100 Bank Account",
        accrue_eosb: bool = True,
        wps_employer_id: str | None = None,
        wps_routing_code: str | None = None,
        wps_employer_ref: str | None = None,
    ) -> str | None:
        """Open the Timesheet modal, configure pay period, account, and WPS SCR fields, preview .SIF, and save."""
        self.click_id("btnOpenTimesheetModal")
        self.wait_until(lambda p: p.locator("#timesheetModal").is_visible())
        self.fill_input("timesheetPeriod", pay_period_yyyy_mm)
        self.select_by_value_or_text("payrollPaymentAccount", payment_account)
        cb = self.page.locator("#payrollAccrueEOSB")
        if cb.is_checked() != bool(accrue_eosb):
            self.click_id("payrollAccrueEOSB")
        if wps_employer_id is not None:
            self.fill_input("wpsEmployerId", wps_employer_id)
        if wps_routing_code is not None:
            self.fill_input("wpsEmployerRoutingCode", wps_routing_code)
        if wps_employer_ref is not None:
            self.fill_input("wpsEmployerRef", wps_employer_ref)
        self.click_id("btnPreviewWpsSif")
        self.last_wps_sif_preview = self.get_text_by_id("wpsSifPreviewBox")
        self.click_id("btnSavePayroll")
        alert_text = self.accept_alert_if_present(timeout=3.0)
        self.fill_input("filterTimesheetMonth", pay_period_yyyy_mm)
        return alert_text

    def simulate_eosb_calculator(
        self,
        basic_salary: str,
        total_salary: str,
        hire_date: str,
        end_date: str,
        unpaid_days: str = "0",
    ) -> str:
        """Populate the Interactive Statutory Gratuity Calculator inputs and return its summary text."""
        self.fill_input("eosbCalcBasicSalary", basic_salary)
        self.fill_input("eosbCalcTotalSalary", total_salary)
        self.fill_input("eosbCalcHireDate", hire_date)
        self.fill_input("eosbCalcEndDate", end_date)
        self.fill_input("eosbCalcUnpaidDays", unpaid_days)
        return self.get_text_by_id("eosbCalcResultSummary")

    def get_saved_timesheets_text(self) -> str:
        """Return the text of `#savedTimesheetsContainer`."""
        return self.get_text_by_id("savedTimesheetsContainer")

    def configure_company_branding(
        self,
        company_name: str,
        company_address: str,
        company_phone: str,
        logo_data_uri: str,
    ) -> None:
        """Populate Company Settings (`#companyName`, `#companyAddress`, `#companyPhone`, logo) and save."""
        self.fill_input("companyName", company_name)
        self.fill_input("companyAddress", company_address)
        self.fill_input("companyPhone", company_phone)
        self.click_id("btnSaveCompanySettings")
        self.accept_alert_if_present(timeout=1.5)
        self.evaluate_script(
            """
            const s = JSON.parse(localStorage.getItem('bookkeeping_settings') || '{}');
            s.companyLogo = arguments[0];
            localStorage.setItem('bookkeeping_settings', JSON.stringify(s));
            const preview = document.getElementById('companyLogoPreview');
            if (preview) { preview.src = arguments[0]; preview.style.display = 'block'; }
            """,
            logo_data_uri,
        )

    def get_timesheet_employee_filter_options(self) -> list[str]:
        """Return all option texts inside `#filterTimesheetEmployee` from the live DOM."""
        self.wait_until(lambda p: p.locator("#filterTimesheetEmployee").count() > 0)
        return self.evaluate_script(
            """
            const sel = document.getElementById('filterTimesheetEmployee');
            return sel ? Array.from(sel.options).map(o => (o.textContent || '').trim()) : [];
            """
        )

    def filter_timesheets_by_employee(self, employee_name: str) -> None:
        """Select the option matching `employee_name` in `#filterTimesheetEmployee`."""
        self.wait_until(lambda p: p.locator("#filterTimesheetEmployee").count() > 0)
        target_value = ""
        if employee_name and employee_name != "All Employees":
            target_value = self.evaluate_script(
                """
                const sel = document.getElementById('filterTimesheetEmployee');
                if (!sel) return '';
                const opt = Array.from(sel.options).find(o => (o.textContent || '').includes(arguments[0]));
                return opt ? (opt.value || '') : '';
                """,
                employee_name,
            )
        self.select_by_value_or_text("filterTimesheetEmployee", target_value)

    def open_payslip_for_employee(self, period: str, employee_name: str) -> dict:
        """Click the `Payslip` button for `employee_name` inside `#savedTimesheetsContainer` and return modal details."""
        self.wait_until(lambda p: p.locator("#savedTimesheetsContainer").count() > 0)
        clicked = self.evaluate_script(
            """
            const container = document.getElementById('savedTimesheetsContainer');
            if (!container) return false;
            for (const row of container.querySelectorAll('tbody tr')) {
                if ((row.innerText || row.textContent || '').includes(arguments[0])) {
                    const btn = row.querySelector('button');
                    if (btn) { btn.click(); return true; }
                }
            }
            return false;
            """,
            employee_name,
        )
        assert clicked, f"Payslip button for '{employee_name}' in period '{period}' not found"
        self.wait_until(lambda p: p.locator("#invoiceModal").is_visible())
        doc_el = self.page.locator("#modalBody")
        modal_el = self.page.locator("#invoiceModal")
        result = {
            "displayed": modal_el.is_visible(),
            "text": doc_el.inner_text(),
            "html": doc_el.inner_html(),
        }
        self.page.locator("#modalFooter .btn-secondary").evaluate("el => el.click()")
        return result

    # --- Fixed Assets (`#view-assets`) ---

    def register_fixed_asset_and_render(
        self,
        description: str,
        location: str,
        purchase_date: str,
        initial_value: float,
        years: int,
    ) -> None:
        """Add a Fixed Asset record and refresh the Fixed Assets Directory."""
        self.evaluate_script(
            """
            const assets = JSON.parse(localStorage.getItem('bookkeeping_assets') || '[]');
            const val = Number(arguments[3]);
            const yrs = Number(arguments[4]);
            assets.push({
                id: String(Date.now()),
                description: arguments[0],
                location: arguments[1],
                purchaseDate: arguments[2],
                initialValue: val,
                years: yrs,
                monthlyDepr: val / (yrs * 12)
            });
            localStorage.setItem('bookkeeping_assets', JSON.stringify(assets));
            if (typeof window.loadAssetsDirectory === 'function') window.loadAssetsDirectory();
            """,
            description,
            location,
            purchase_date,
            initial_value,
            years,
        )

    def get_assets_directory_text(self) -> str:
        """Return the text of `#assetsDirectoryBody`."""
        self.evaluate_script(
            "if (typeof window.loadAssetsDirectory === 'function') window.loadAssetsDirectory();"
        )
        return self.get_text_by_id("assetsDirectoryBody")
