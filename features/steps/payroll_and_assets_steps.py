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
    if not hasattr(context, "employee_name_map"):
        context.employee_name_map = {}
    context.employee_name_map[emp_name] = unique_name
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
    unique_names = getattr(context, "employee_name_map", {})
    unique_name = unique_names.get(emp_name, getattr(context, "last_employee_name", emp_name))
    table_text = context.payroll_page.get_employee_directory_text()
    assert unique_name in table_text and expected_total in table_text, (
        f"Expected employee '{unique_name}' with total pay '{expected_total}' in directory, got:\n{table_text}"
    )


@then('the EOSB Summary should display an accrued gratuity balance for "{emp_name}"')
def step_verify_eosb_summary(context, emp_name: str) -> None:
    unique_names = getattr(context, "employee_name_map", {})
    unique_name = unique_names.get(emp_name, getattr(context, "last_employee_name", emp_name))
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
    for prefix in ("Payroll Gross", "Payroll Net", "Payroll Loans", "Payroll Deductions", "EOSB Accrual"):
        context.created_resources.append(("ledger", f"{prefix} {period}"))
    context.payroll_page.process_and_save_payroll(
        pay_period_yyyy_mm=period,
        payment_account=payment_account,
        accrue_eosb=True,
        wps_employer_id="1002233445566",
        wps_routing_code="302620122",
        wps_employer_ref=f"WPS-{period}",
    )


@then('the WPS SIF preview should contain an "{edr_tag}" record and a MOHRE "{scr_tag}" control record for "{salary_month}"')
def step_verify_wps_sif_preview(context, edr_tag: str, scr_tag: str, salary_month: str) -> None:
    sif_text = getattr(context.payroll_page, "last_wps_sif_preview", "")
    assert f"{edr_tag}," in sif_text, f"Expected '{edr_tag},' in WPS SIF preview, got:\n{sif_text}"
    assert f"{scr_tag},1002233445566,302620122," in sif_text and f",{salary_month}," in sif_text, (
        f"Expected MOHRE '{scr_tag}' header with salary month '{salary_month}', got:\n{sif_text}"
    )


@when(
    'the user simulates statutory gratuity for basic salary "{basic}" AED, total salary "{total}" AED, hired "{hire_date}", ending "{end_date}" with "{unpaid_days}" unpaid leave days'
)
def step_simulate_statutory_gratuity(
    context,
    basic: str,
    total: str,
    hire_date: str,
    end_date: str,
    unpaid_days: str,
) -> None:
    context.last_eosb_calc_summary = context.payroll_page.simulate_eosb_calculator(
        basic_salary=basic,
        total_salary=total,
        hire_date=hire_date,
        end_date=end_date,
        unpaid_days=unpaid_days,
    )


@then('the statutory gratuity calculator should show "{expected_bracket}" and statutory entitlement "{expected_amount}"')
def step_verify_statutory_gratuity_calculator(
    context,
    expected_bracket: str,
    expected_amount: str,
) -> None:
    summary = getattr(context, "last_eosb_calc_summary", "")
    assert expected_bracket in summary, f"Expected bracket '{expected_bracket}' in calculator summary, got:\n{summary}"
    assert expected_amount in summary, f"Expected entitlement '{expected_amount}' in calculator summary, got:\n{summary}"


@then('the saved timesheets section for "{period}" should list "{emp_name}"')
def step_verify_saved_timesheet(context, period: str, emp_name: str) -> None:
    unique_names = getattr(context, "employee_name_map", {})
    unique_name = unique_names.get(emp_name, getattr(context, "last_employee_name", emp_name))
    saved_text = context.payroll_page.get_saved_timesheets_text()
    assert unique_name in saved_text, (
        f"Expected '{unique_name}' in saved timesheets for {period}, got:\n{saved_text[:500]}"
    )


@when('the user filters the saved timesheets by employee "{emp_name}"')
def step_filter_saved_timesheets_by_employee(context, emp_name: str) -> None:
    unique_names = getattr(context, "employee_name_map", {})
    target_name = "All Employees" if emp_name == "All Employees" else unique_names.get(emp_name, emp_name)
    context.payroll_page.filter_timesheets_by_employee(target_name)


@then('the filtered timesheets section for "{period}" should list "{included_emp}" and exclude "{excluded_emp}"')
def step_verify_filtered_saved_timesheet(
    context,
    period: str,
    included_emp: str,
    excluded_emp: str,
) -> None:
    unique_names = getattr(context, "employee_name_map", {})
    inc_name = unique_names.get(included_emp, included_emp)
    exc_name = unique_names.get(excluded_emp, excluded_emp)
    saved_text = context.payroll_page.get_saved_timesheets_text()
    assert inc_name in saved_text, (
        f"Expected '{inc_name}' in filtered saved timesheets for {period}, got:\n{saved_text[:500]}"
    )
    assert exc_name not in saved_text, (
        f"Expected '{exc_name}' to be excluded from filtered saved timesheets for {period}, got:\n{saved_text[:500]}"
    )


@when(
    'the user configures company branding with name "{company_name}", address "{company_address}", contact number "{company_phone}", and a company logo'
)
def step_configure_company_branding(
    context,
    company_name: str,
    company_address: str,
    company_phone: str,
) -> None:
    logo_svg_data_uri = (
        "data:image/svg+xml;utf8,"
        "<svg xmlns='http://www.w3.org/2000/svg' width='120' height='40'>"
        "<rect width='120' height='40' rx='6' fill='%230f172a'/>"
        "<text x='14' y='25' fill='%23ffffff' font-family='sans-serif' font-size='14' font-weight='bold'>AL NOOR</text>"
        "</svg>"
    )
    context.payroll_page.configure_company_branding(
        company_name=company_name,
        company_address=company_address,
        company_phone=company_phone,
        logo_data_uri=logo_svg_data_uri,
    )


@then('the Timesheet employee filter dropdown should include both "{emp_one}" and "{emp_two}"')
def step_verify_timesheet_employee_filter_options(
    context,
    emp_one: str,
    emp_two: str,
) -> None:
    unique_names = getattr(context, "employee_name_map", {})
    name_one = unique_names.get(emp_one, emp_one)
    name_two = unique_names.get(emp_two, emp_two)
    options = context.payroll_page.get_timesheet_employee_filter_options()
    joined = " | ".join(options)
    assert any(name_one in opt for opt in options), (
        f"Expected '{name_one}' in Timesheet employee filter options, got: {joined}"
    )
    assert any(name_two in opt for opt in options), (
        f"Expected '{name_two}' in Timesheet employee filter options, got: {joined}"
    )


@when('the user opens the payslip for "{emp_name}" in period "{period}"')
def step_open_payslip_for_employee(context, emp_name: str, period: str) -> None:
    unique_names = getattr(context, "employee_name_map", {})
    unique_name = unique_names.get(emp_name, getattr(context, "last_employee_name", emp_name))
    context.last_payslip_modal = context.payroll_page.open_payslip_for_employee(
        period=period,
        employee_name=unique_name,
    )


@then(
    'the professional payslip document should display employee "{emp_name}", designation "{designation}", starting date "{start_date}", company "{company_name}", address "{company_address}", contact number "{company_phone}", and the company logo'
)
def step_verify_professional_payslip_document(
    context,
    emp_name: str,
    designation: str,
    start_date: str,
    company_name: str,
    company_address: str,
    company_phone: str,
) -> None:
    unique_names = getattr(context, "employee_name_map", {})
    unique_name = unique_names.get(emp_name, getattr(context, "last_employee_name", emp_name))
    modal_info = getattr(context, "last_payslip_modal", {})
    assert modal_info.get("displayed"), "Expected payslip preview modal (#invoiceModal) to be displayed"
    doc_text = modal_info.get("text", "")
    doc_html = modal_info.get("html", "")
    for expected in (unique_name, designation, start_date, company_name, company_address, company_phone):
        assert expected in doc_text, f"Expected '{expected}' in payslip text, got:\n{doc_text}"
    for excluded in ("Unpaid Leave:", "Labour Card / WPS:", "IBAN / Routing:", "Disbursement Mode:", "1100 Bank Account"):
        assert excluded not in doc_text, f"Did not expect '{excluded}' in payslip text, got:\n{doc_text}"
    assert "payslip-company-logo" in doc_html and "data:image/svg+xml" in doc_html, (
        f"Expected company logo image in payslip HTML, got:\n{doc_html[:500]}"
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
