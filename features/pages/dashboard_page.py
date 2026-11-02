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
