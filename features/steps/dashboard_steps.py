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


@then('the dashboard UAE Corporate Tax tracker should show regime status "{expected_status}" and estimated tax "{expected_tax}"')
def step_verify_corp_tax_tracker_status_and_tax(context, expected_status: str, expected_tax: str) -> None:
    summary = context.dashboard_page.get_corp_tax_tracker_summary()
    assert expected_status in summary["status_badge"], (
        f"Expected CT tracker status badge to contain '{expected_status}', got '{summary['status_badge']}'"
    )
    assert summary["estimated_tax"] == expected_tax, (
        f"Expected CT tracker estimated tax '{expected_tax}', got '{summary['estimated_tax']}'"
    )


@then('the dashboard UAE Corporate Tax tracker Small Business Relief status should contain "{expected_sbr}"')
def step_verify_corp_tax_tracker_sbr_status(context, expected_sbr: str) -> None:
    summary = context.dashboard_page.get_corp_tax_tracker_summary()
    assert expected_sbr in summary["sbr_status"], (
        f"Expected CT tracker SBR status to contain '{expected_sbr}', got '{summary['sbr_status']}'"
    )


def _offset_date_iso(days_offset: int) -> str:
    from datetime import datetime, timedelta, timezone
    target = datetime.now(timezone.utc).date() + timedelta(days=int(days_offset))
    return target.isoformat()


@when('the user configures UAE compliance renewal dates with Trade License "{tl_num}" expiring in "{tl_days}" days and Establishment Card "{est_num}" expiring in "{est_days}" days')
def step_configure_company_compliance_dates(context, tl_num: str, tl_days: str, est_num: str, est_days: str) -> None:
    context.dashboard_page.configure_company_compliance_dates(
        trade_license_num=tl_num,
        trade_license_expiry=_offset_date_iso(int(tl_days)),
        est_card_num=est_num,
        est_card_expiry=_offset_date_iso(int(est_days)),
    )


@when('the user adds an employee "{emp_name}" with position "{position}", basic salary "{basic_salary}", Visa expiring in "{visa_days}" days, and Emirates ID expiring in "{eid_days}" days')
def step_add_employee_with_compliance_dates(
    context,
    emp_name: str,
    position: str,
    basic_salary: str,
    visa_days: str,
    eid_days: str,
) -> None:
    unique_name = f"{emp_name} {context.scenario_uid}"
    context.compliance_emp_name = unique_name
    context.created_resources.append(("employee", unique_name))
    context.dashboard_page.add_employee_with_compliance_dates(
        name=unique_name,
        position=position,
        basic_salary=basic_salary,
        visa_expiry=_offset_date_iso(int(visa_days)),
        eid_expiry=_offset_date_iso(int(eid_days)),
    )


@then('the dashboard UAE Compliance Reminder widget should show Trade License status containing "{expected_tl}" and Establishment Card status containing "{expected_est}"')
def step_verify_compliance_tl_and_est_status(context, expected_tl: str, expected_est: str) -> None:
    summary = context.dashboard_page.get_compliance_reminder_summary()
    assert expected_tl in summary["trade_license_badge"], (
        f"Expected Trade License badge to contain '{expected_tl}', got '{summary['trade_license_badge']}'"
    )
    assert expected_est in summary["est_card_badge"], (
        f"Expected Establishment Card badge to contain '{expected_est}', got '{summary['est_card_badge']}'"
    )


@then('the dashboard UAE Compliance Reminder widget should list employee "{emp_name}" with "{alert_one}" and "{alert_two}" alerts')
def step_verify_compliance_employee_alerts(context, emp_name: str, alert_one: str, alert_two: str) -> None:
    summary = context.dashboard_page.get_compliance_reminder_summary()
    list_text = summary["employee_list_text"]
    expected_name = getattr(context, "compliance_emp_name", emp_name)
    assert expected_name in list_text, (
        f"Expected employee '{expected_name}' in compliance alerts list, got '{list_text}'"
    )
    assert alert_one in list_text, (
        f"Expected alert '{alert_one}' in compliance alerts list, got '{list_text}'"
    )
    assert alert_two in list_text, (
        f"Expected alert '{alert_two}' in compliance alerts list, got '{list_text}'"
    )
