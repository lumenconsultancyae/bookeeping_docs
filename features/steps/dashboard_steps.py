"""Step definitions for the Executive Dashboard (`dashboard_and_kpis.feature`)."""

from __future__ import annotations

import re
from behave import then, when


def _parse_currency(val: str) -> float:
    cleaned = re.sub(r"[^0-9.-]", "", val or "")
    return float(cleaned) if cleaned else 0.0


@when('the user selects the dashboard period year "{year_val}" and month "{month_val}"')
def step_select_dashboard_period(context, year_val: str, month_val: str) -> None:
    context.dashboard_page.select_dashboard_period(year_val, month_val)


@then('the dashboard page title should be "{expected_title}"')
def step_verify_dashboard_title(context, expected_title: str) -> None:
    actual_title = context.base_page.get_active_page_title()
    assert actual_title == expected_title, (
        f"Expected page title '{expected_title}', got '{actual_title}'"
    )


@then("the 6-month cash flow chart should be rendered")
def step_verify_cashflow_chart(context) -> None:
    assert context.dashboard_page.is_cashflow_chart_rendered(), (
        "Expected #cashFlowChart canvas to be rendered with non-zero dimensions"
    )


@then('the dashboard KPI "{kpi_name}" should display a formatted currency value')
def step_verify_kpi_formatted(context, kpi_name: str) -> None:
    val = context.dashboard_page.get_kpi_value(kpi_name)
    assert re.search(r"\d+\.\d{2}", val), (
        f"Expected KPI '{kpi_name}' to show formatted currency, got '{val}'"
    )


@then('the dashboard KPI "{kpi_name}" should reflect a positive balance')
def step_verify_kpi_positive(context, kpi_name: str) -> None:
    val = context.dashboard_page.get_kpi_value(kpi_name)
    numeric = _parse_currency(val)
    assert numeric > 0, (
        f"Expected KPI '{kpi_name}' to be > 0, got '{val}' ({numeric})"
    )


@when("the user opens the Total Expenses Breakdown modal")
def step_open_expense_breakdown(context) -> None:
    context.dashboard_page.open_expense_breakdown_modal()


@then("the Total Expenses Breakdown modal should show a non-zero total")
def step_verify_expense_breakdown_total(context) -> None:
    total_str = context.dashboard_page.get_expense_breakdown_total()
    assert _parse_currency(total_str) > 0, (
        f"Expected non-zero expense breakdown total, got '{total_str}'"
    )
    context.base_page.dismiss_modals_if_present()
