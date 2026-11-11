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
    context.base_page.record_settings_snapshot(context.created_resources)
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
    if not hasattr(context, "compliance_emp_map"):
        context.compliance_emp_map = {}
    context.compliance_emp_map[emp_name] = unique_name
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
    emp_map = getattr(context, "compliance_emp_map", {})
    expected_name = emp_map.get(emp_name, getattr(context, "compliance_emp_name", emp_name))
    assert expected_name in list_text, (
        f"Expected employee '{expected_name}' in compliance alerts list, got '{list_text}'"
    )
    assert alert_one in list_text, (
        f"Expected alert '{alert_one}' in compliance alerts list, got '{list_text}'"
    )
    assert alert_two in list_text, (
        f"Expected alert '{alert_two}' in compliance alerts list, got '{list_text}'"
    )


@then('the dashboard UAE Compliance Reminder widget should not list employee "{excluded_emp}"')
def step_verify_compliance_employee_excluded(context, excluded_emp: str) -> None:
    summary = context.dashboard_page.get_compliance_reminder_summary()
    list_text = summary["employee_list_text"]
    emp_map = getattr(context, "compliance_emp_map", {})
    excluded_name = emp_map.get(excluded_emp, excluded_emp)
    assert excluded_name not in list_text, (
        f"Expected employee '{excluded_name}' (>10d before expiry) to be excluded from dashboard compliance alerts, got '{list_text}'"
    )


@when('the user registers an upcoming PDC cheque "{cheque_number}" for supplier "{supplier_name}" of "{amount}" AED clearing in "{days_offset}" days')
def step_register_upcoming_pdc_cheque(
    context,
    cheque_number: str,
    supplier_name: str,
    amount: str,
    days_offset: str,
) -> None:
    unique_cheque = f"{cheque_number}-{context.scenario_uid}"
    clear_date = _offset_date_iso(int(days_offset))
    context.pdc_cheque_number = unique_cheque
    context.pdc_supplier_name = supplier_name
    context.pdc_clear_date = clear_date
    context.created_resources.append(("cheque", unique_cheque))
    context.contacts_page.register_cheque(
        cheque_number=unique_cheque,
        created_date=_offset_date_iso(0),
        cheque_date=clear_date,
        amount=amount,
        supplier_name=supplier_name,
        bank_account="Emirates NBD",
    )


@then('the dashboard Upcoming PDC Cheques reminder should display supplier "{supplier_name}" with clearing date in "{days_offset}" days and amount "{expected_amount}"')
def step_verify_dashboard_pdc_reminder(
    context,
    supplier_name: str,
    days_offset: str,
    expected_amount: str,
) -> None:
    iso_date = _offset_date_iso(int(days_offset))
    expected_date = f"{iso_date[8:10]}/{iso_date[5:7]}/{iso_date[2:4]}"
    summary = context.dashboard_page.get_pdc_reminder_summary()
    list_text = summary["list_text"]
    assert supplier_name in list_text, (
        f"Expected supplier '{supplier_name}' in PDC reminder list, got '{list_text}'"
    )
    assert expected_date in list_text, (
        f"Expected clearing date '{expected_date}' in PDC reminder list, got '{list_text}'"
    )
    assert expected_amount in list_text, (
        f"Expected amount '{expected_amount}' in PDC reminder list, got '{list_text}'"
    )


@then('the dashboard Upcoming PDC Cheques reminder should not display supplier "{excluded_supplier}"')
def step_verify_dashboard_pdc_reminder_excludes(context, excluded_supplier: str) -> None:
    summary = context.dashboard_page.get_pdc_reminder_summary()
    list_text = summary["list_text"]
    assert excluded_supplier not in list_text, (
        f"Expected supplier '{excluded_supplier}' (>30 days) to be excluded from PDC reminder list, got '{list_text}'"
    )


@when("the user toggles the sidebar menu collapse button")
def step_toggle_sidebar_collapse(context) -> None:
    context.dashboard_page.toggle_sidebar_collapse()


@then('the collapsed sidebar menu should display SVG icons for "{view_target}" and "{second_target}" instead of text monograms')
def step_verify_collapsed_sidebar_svg_icons(context, view_target: str, second_target: str) -> None:
    for target in (view_target, second_target):
        state = context.dashboard_page.get_sidebar_menu_icon_state(target)
        assert state.get("is_collapsed") is True, (
            f"Expected body.sidebar-collapsed to be active when checking '{target}', got {state}"
        )
        assert state.get("has_svg") is True, (
            f"Expected sidebar item '{target}' to contain an <svg> icon, got {state}"
        )
        assert float(state.get("svg_width", 0)) > 0 and float(state.get("svg_height", 0)) > 0, (
            f"Expected sidebar item '{target}' SVG icon to have visible dimensions, got {state}"
        )
        assert state.get("before_display") == "none" or state.get("before_content") in ("none", ""), (
            f"Expected ::before text monogram to be suppressed for '{target}', got {state}"
        )
