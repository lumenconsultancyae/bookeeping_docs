"""Page Object for the Executive Dashboard view (`#view-dashboard`)."""

from __future__ import annotations

from selenium.webdriver.common.by import By

from features.pages.base_page import BasePage


class DashboardPage(BasePage):
    """UI adapter for reading Dashboard KPIs, filtering periods, and opening breakdowns."""

    KPI_ID_MAP = {
        "Cash Runway": "kpiRunway",
        "Avg. Monthly Burn": "kpiBurnRate",
        "Net Profit Margin": "kpiMargin",
        "Current Cash": "kpiBankBalanceHero",
        "Total A/R": "kpiReceivable",
        "Total A/P": "kpiAccountsPayable",
        "Total Revenue": "kpiRevenue",
        "Total Expenses": "kpiExpenses",
        "VAT Summary": "kpiVat",
        "Corp. Tax Liab.": "kpiCorpTax",
        "Net Profit / (Loss)": "kpiNetProfit",
    }

    def select_dashboard_period(self, year_value: str, month_value: str = "all") -> None:
        """Select the dashboard year and month filters and refresh KPIs."""
        self.select_by_value_or_text("dashboardYearFilter", year_value)
        if year_value != "all":
            self.select_by_value_or_text("dashboardMonthFilter", month_value)

    def get_kpi_value(self, kpi_label: str) -> str:
        """Return the displayed value of a named Dashboard KPI card."""
        element_id = self.KPI_ID_MAP[kpi_label]
        return self.get_text_by_id(element_id)

    def is_cashflow_chart_rendered(self) -> bool:
        """Return True if the `#cashFlowChart` canvas is visible and has non-zero dimensions."""
        return bool(
            self.wait_until(
                lambda d: d.execute_script(
                    """
                    const c = document.getElementById('cashFlowChart');
                    return Boolean(c && c.offsetWidth > 0 && c.offsetHeight > 0);
                    """
                )
            )
        )

    def open_expense_breakdown_modal(self) -> None:
        """Open the Total Expenses Breakdown modal from the Dashboard."""
        self.driver.execute_script("window.openExpenseBreakdown();")
        self.wait_until(
            lambda d: d.find_element(By.ID, "expenseBreakdownModal").is_displayed()
        )

    def get_expense_breakdown_total(self) -> str:
        """Return the total amount displayed in `#expenseBreakdownTotal`."""
        return self.get_text_by_id("expenseBreakdownTotal")

    def get_corp_tax_tracker_summary(self) -> dict[str, str]:
        """Return the live values displayed inside the Home Dashboard UAE Corporate Tax Tracker card."""
        self.driver.execute_script(
            "const el = document.getElementById('corpTaxTrackerCard'); if (el) el.scrollIntoView({ block: 'center' });"
        )
        return {
            "status_badge": self.get_text_by_id("ctTrackerStatusBadge"),
            "taxable_income": self.get_text_by_id("ctTrackerTaxableIncome"),
            "threshold_pct": self.get_text_by_id("ctTrackerThresholdPct"),
            "sbr_status": self.get_text_by_id("ctTrackerSbrStatus"),
            "sbr_revenue": self.get_text_by_id("ctTrackerSbrRevenue"),
            "estimated_tax": self.get_text_by_id("ctTrackerEstimatedTax"),
            "effective_rate": self.get_text_by_id("ctTrackerEffectiveRate"),
        }

    def configure_company_compliance_dates(
        self,
        trade_license_num: str,
        trade_license_expiry: str,
        est_card_num: str,
        est_card_expiry: str,
    ) -> None:
        """Fill and save Trade License and Establishment Card expiry dates in `#view-settings`."""
        self.fill_input("settingTradeLicenseNumber", trade_license_num)
        self.fill_input("settingTradeLicenseExpiry", trade_license_expiry)
        self.fill_input("settingEstablishmentCardNumber", est_card_num)
        self.fill_input("settingEstablishmentCardExpiry", est_card_expiry)
        self.click_id("btnSaveTaxSettings")
        self.dismiss_any_alert()

    def add_employee_with_compliance_dates(
        self,
        name: str,
        position: str,
        basic_salary: str,
        visa_expiry: str,
        eid_expiry: str,
    ) -> None:
        """Open `#addEmployeeModal`, fill employee and Visa/EID expiry dates, and submit."""
        self.driver.execute_script("window.openAddEmployeeModal();")
        self.wait_until(lambda d: d.find_element(By.ID, "addEmployeeModal").is_displayed())
        self.fill_input("dirEmpName", name)
        self.fill_input("dirEmpPosition", position)
        self.fill_input("dirEmpBasic", basic_salary)
        self.fill_input("dirEmpVisaExpiry", visa_expiry)
        self.fill_input("dirEmpEmiratesIdExpiry", eid_expiry)
        self.driver.execute_script(
            "document.querySelector('#addEmployeeForm button[type=\"submit\"]').click();"
        )
        self.dismiss_any_alert()

    def get_compliance_reminder_summary(self) -> dict[str, str]:
        """Return the live status texts displayed in `#uaeComplianceReminderCard`."""
        self.driver.execute_script(
            "const el = document.getElementById('uaeComplianceReminderCard'); if (el) el.scrollIntoView({ block: 'center' });"
        )
        return {
            "overall_badge": self.get_text_by_id("complianceOverallBadge"),
            "trade_license_badge": self.get_text_by_id("compTradeLicenseBadge"),
            "trade_license_expiry": self.get_text_by_id("compTradeLicenseExpiry"),
            "est_card_badge": self.get_text_by_id("compEstCardBadge"),
            "est_card_expiry": self.get_text_by_id("compEstCardExpiry"),
            "employee_badge": self.get_text_by_id("compEmployeeAlertsBadge"),
            "employee_list_text": self.get_text_by_id("compEmployeeAlertsList"),
        }
