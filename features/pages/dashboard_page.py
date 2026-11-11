"""Page Object for the Executive Dashboard view (`#view-dashboard`)."""

from __future__ import annotations

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
                lambda _p: self.evaluate_script(
                    """
                    const c = document.getElementById('cashFlowChart');
                    return Boolean(c && c.offsetWidth > 0 && c.offsetHeight > 0);
                    """
                )
            )
        )

    def open_expense_breakdown_modal(self) -> None:
        """Open the Total Expenses Breakdown modal from the Dashboard."""
        self.evaluate_script("window.openExpenseBreakdown();")
        self.wait_until(
            lambda p: p.locator("#expenseBreakdownModal").is_visible()
        )

    def get_expense_breakdown_total(self) -> str:
        """Return the total amount displayed in `#expenseBreakdownTotal`."""
        return self.get_text_by_id("expenseBreakdownTotal")

    def get_corp_tax_tracker_summary(self) -> dict[str, str]:
        """Return the live values displayed inside the Home Dashboard UAE Corporate Tax Tracker card."""
        self.evaluate_script(
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
        self.click_id("btnOpenAddEmployee")
        self.wait_until(lambda p: p.locator("#addEmployeeModal").is_visible())
        self.fill_input("dirEmpName", name)
        self.fill_input("dirEmpPosition", position)
        self.fill_input("dirEmpBasic", basic_salary)
        self.fill_input("dirEmpVisaExpiry", visa_expiry)
        self.fill_input("dirEmpEmiratesIdExpiry", eid_expiry)
        self.page.locator('#addEmployeeForm button[type="submit"]').click()
        self.dismiss_any_alert()
        self.wait_until(lambda p: not p.locator("#addEmployeeModal").is_visible())

    def get_compliance_reminder_summary(self) -> dict[str, str]:
        """Return the live status texts displayed in `#uaeComplianceReminderCard`."""
        self.evaluate_script(
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

    def get_pdc_reminder_summary(self) -> dict[str, str]:
        """Return the live badge and list text inside `#pdcReminderCard` on the Dashboard."""
        self.evaluate_script(
            "const el = document.getElementById('pdcReminderCard'); if (el) el.scrollIntoView({ block: 'center' });"
        )
        return {
            "badge": self.get_text_by_id("pdcReminderBadge"),
            "list_text": self.get_text_by_id("pdcReminderList"),
        }

    def toggle_sidebar_collapse(self) -> None:
        """Click `#btnSidebarToggle` to collapse or expand the sidebar navigation."""
        self.click_id("btnSidebarToggle")

    def get_sidebar_menu_icon_state(self, view_target: str) -> dict[str, object]:
        """Return collapsed state and SVG icon dimensions for a `.nav-item[data-target]` link."""
        result = self.evaluate_script(
            """
            const target = arguments[0];
            const isCollapsed = document.body.classList.contains('sidebar-collapsed');
            const item = document.querySelector(`.sidebar .nav-item[data-target="${target}"]`);
            if (!item) return { is_collapsed: isCollapsed, found: false };
            const parentGroup = item.closest('.nav-dropdown');
            if (parentGroup && !parentGroup.classList.contains('open')) {
                const header = parentGroup.querySelector('.nav-dropdown-header');
                if (header) header.click();
            }
            const svg = item.querySelector('svg');
            const svgRect = svg ? svg.getBoundingClientRect() : { width: 0, height: 0 };
            const beforeStyle = window.getComputedStyle(item, '::before');
            return {
                is_collapsed: isCollapsed,
                found: true,
                has_svg: Boolean(svg),
                svg_width: svgRect.width,
                svg_height: svgRect.height,
                before_display: beforeStyle ? beforeStyle.display : '',
                before_content: beforeStyle ? beforeStyle.content : ''
            };
            """,
            view_target,
        )
        return dict(result or {})
