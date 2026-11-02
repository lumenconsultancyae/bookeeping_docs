"""Step definitions for Employee Directory, UAE WPS Payroll, EOSB Gratuity, and Fixed Assets."""

from __future__ import annotations

from behave import then, when


@when(
    'the user adds an employee named "{emp_name}" as "{position}" hired on "{date_hired}" with basic salary "{basic}" and housing allowance "{housing}"'
)
def step_add_employee(
    context,
    emp_name: str,
    position: str,
    date_hired: str,
    basic: str,
    housing: str,
) -> None:
    unique_name = f"{emp_name} {context.scenario_uid}"
    context.last_employee_name = unique_name
    context.created_resources.append(("employee", unique_name))

    context.payroll_page.add_employee(
        name=unique_name,
        position=position,
        date_hired=date_hired,
        labour_card=f"LC-{context.scenario_uid[:6]}",
        iban="AE070331234567890123456",
        routing_code="302620122",
        basic_salary=basic,
        housing_allowance=housing,
    )


@then('the Employee Directory should list "{emp_name}" with total pay "{expected_total}"')
def step_verify_employee_in_directory(
    context,
    emp_name: str,
    expected_total: str,
) -> None:
    unique_name = getattr(context, "last_employee_name", emp_name)
    table_text = context.payroll_page.get_employee_directory_text()
    assert unique_name in table_text and expected_total in table_text, (
        f"Expected employee '{unique_name}' with total pay '{expected_total}' in directory, got:\n{table_text}"
    )


@then('the EOSB Summary should display an accrued gratuity balance for "{emp_name}"')
def step_verify_eosb_summary(context, emp_name: str) -> None:
    unique_name = getattr(context, "last_employee_name", emp_name)
    eosb_text = context.payroll_page.get_eosb_summary_text()
    assert unique_name in eosb_text, (
        f"Expected employee '{unique_name}' in EOSB Summary, got:\n{eosb_text}"
    )


@when(
    'the user processes and saves the payroll run for period "{period}" paid from "{payment_account}" with EOSB accrual enabled'
)
def step_process_and_save_payroll(
    context,
    period: str,
    payment_account: str,
) -> None:
    context.created_resources.append(("payroll", period))
    context.created_resources.append(("ledger", f"PAY-{period}"))
    context.created_resources.append(("ledger", f"EOSB-{period}"))
    context.created_resources.append(("ledger", f"LEAVE-{period}"))
    context.payroll_page.process_and_save_payroll(
        pay_period_yyyy_mm=period,
        payment_account=payment_account,
        accrue_eosb=True,
    )


@then('the saved timesheets section for "{period}" should list "{emp_name}"')
def step_verify_saved_timesheet(context, period: str, emp_name: str) -> None:
    unique_name = getattr(context, "last_employee_name", emp_name)
    saved_text = context.payroll_page.get_saved_timesheets_text()
    assert unique_name in saved_text, (
        f"Expected '{unique_name}' in saved timesheets for {period}, got:\n{saved_text[:500]}"
    )


@when(
    'a fixed asset "{asset_desc}" located in "{location}" purchased on "{purchase_date}" for "{initial_value}" AED over "{years}" years is registered'
)
def step_register_fixed_asset(
    context,
    asset_desc: str,
    location: str,
    purchase_date: str,
    initial_value: str,
    years: str,
) -> None:
    unique_desc = f"{asset_desc} {context.scenario_uid}"
    context.last_asset_desc = unique_desc
    context.created_resources.append(("asset", unique_desc))

    context.payroll_page.register_fixed_asset_and_render(
        description=unique_desc,
        location=location,
        purchase_date=purchase_date,
        initial_value=float(initial_value),
        years=int(years),
    )


@then(
    'the Fixed Assets Directory should list "{asset_desc}" with monthly depreciation "{expected_monthly}"'
)
def step_verify_fixed_asset_in_directory(
    context,
    asset_desc: str,
    expected_monthly: str,
) -> None:
    unique_desc = getattr(context, "last_asset_desc", asset_desc)
    table_text = context.payroll_page.get_assets_directory_text()
    assert unique_desc in table_text and expected_monthly in table_text, (
        f"Expected fixed asset '{unique_desc}' with monthly depr '{expected_monthly}', got:\n{table_text}"
    )
