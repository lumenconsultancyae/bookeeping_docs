"""Step definitions for Financial Statements, UAE VAT 201, Corporate Tax, Budgeting, Forecast, Audit Log, and Settings."""

from __future__ import annotations

import re
from behave import then, when


def _parse_currency(val: str) -> float:
    cleaned = re.sub(r"[^0-9.-]", "", val or "")
    return float(cleaned) if cleaned else 0.0


@then("the Trial Balance total debits should equal total credits")
def step_verify_trial_balance_equilibrium(context) -> None:
    tb = context.reports_page.get_trial_balance_totals()
    debit = _parse_currency(tb["debit"])
    credit = _parse_currency(tb["credit"])
    assert debit > 0 and abs(debit - credit) < 0.01, (
        f"Expected Trial Balance equilibrium (Debit == Credit > 0), got Debit={tb['debit']} Credit={tb['credit']}"
    )


@then('the Income Statement should display "{heading_one}" and "{heading_two}"')
def step_verify_income_statement(context, heading_one: str, heading_two: str) -> None:
    text = context.reports_page.get_income_statement_text()
    assert heading_one in text and heading_two in text, (
        f"Expected '{heading_one}' and '{heading_two}' in Income Statement, got:\n{text[:500]}"
    )


@then('the Balance Sheet should display "{heading_one}" and "{heading_two}"')
def step_verify_balance_sheet(context, heading_one: str, heading_two: str) -> None:
    text = context.reports_page.get_balance_sheet_text()
    assert heading_one in text and heading_two in text, (
        f"Expected '{heading_one}' and '{heading_two}' in Balance Sheet, got:\n{text[:500]}"
    )


@then('the Cash Flow Statement should display "{heading_one}" and "{heading_two}"')
def step_verify_cashflow_statement(context, heading_one: str, heading_two: str) -> None:
    text = context.reports_page.get_cashflow_statement_text()
    assert heading_one in text and heading_two in text, (
        f"Expected '{heading_one}' and '{heading_two}' in Cash Flow Statement, got:\n{text[:500]}"
    )


@then("the UAE VAT Return Summary should display formatted Output VAT, Input VAT, and Net VAT values")
def step_verify_vat_return_summary(context) -> None:
    vat = context.reports_page.get_vat_return_summary()
    for key in ("output_vat", "input_vat", "net_vat", "box1", "box9", "box14"):
        assert re.search(r"\d+\.\d{2}", vat[key]), (
            f"Expected formatted currency in VAT field '{key}', got '{vat[key]}'"
        )


@when('the user clicks the "Export FTA Audit File (FAF)" button in the Tax module')
def step_click_export_fta_audit_file(context) -> None:
    context.last_faf_export = context.reports_page.export_fta_audit_file()


@then(
    "the exported FTA Audit File CSV should contain Company Header, Master Data, Purchase Lines, Sales Lines, and balanced General Ledger entries"
)
def step_verify_exported_fta_audit_file_csv(context) -> None:
    export = getattr(context, "last_faf_export", None) or {}
    csv_text = export.get("csv", "")
    assert export.get("filename", "").endswith(".csv"), (
        f"Expected .csv filename from Export FTA Audit File (FAF), got '{export.get('filename')}'"
    )
    for marker in (
        "CompInfo",
        "CompEnd",
        "MasterData",
        "MasterDataEnd",
        "PurcData",
        "PurcDataEnd",
        "SuppData",
        "SuppDataEnd",
        "GLData",
        "GLDataEnd",
    ):
        assert marker in csv_text, f"Expected FTA Audit File marker '{marker}' in exported CSV"
    gl_debit = _parse_currency(export.get("gl_debit", "0"))
    gl_credit = _parse_currency(export.get("gl_credit", "0"))
    assert gl_debit > 0 and abs(gl_debit - gl_credit) < 0.01, (
        f"Expected balanced GLData debits/credits > 0, got debit={gl_debit} credit={gl_credit}"
    )


@then("the UAE Corporate Tax Summary should reflect a positive Add-Backs balance")
def step_verify_corporate_tax_add_backs(context) -> None:
    ct = context.reports_page.get_corporate_tax_summary()
    add_backs = _parse_currency(ct["add_backs"])
    assert add_backs >= 1000.0, (
        f"Expected Corporate Tax Add-Backs >= 1000.0, got '{ct['add_backs']}'"
    )


@when(
    'the user sets a monthly budget for period "{month_period}" on account "{account_name}" of "{budget_amount}" AED'
)
def step_set_monthly_budget(
    context,
    month_period: str,
    account_name: str,
    budget_amount: str,
) -> None:
    context.created_resources.append(("budget", month_period))
    context.reports_page.set_budget_for_account_and_save(
        month_yyyy_mm=month_period,
        account_name=account_name,
        budget_amount=budget_amount,
    )


@then(
    'the Budgeting vs. Actuals table should show account "{account_name}" with status "{expected_status}"'
)
def step_verify_budget_status(
    context,
    account_name: str,
    expected_status: str,
) -> None:
    table_text = context.reports_page.get_budgeting_table_text()
    assert account_name in table_text and expected_status in table_text, (
        f"Expected '{account_name}' with status '{expected_status}' in Budgeting table, got:\n{table_text[:500]}"
    )


@then('the 90-day Cash Flow Forecast table should display "{expected_label}"')
def step_verify_cashflow_forecast(context, expected_label: str) -> None:
    forecast_text = context.reports_page.get_cashflow_forecast_text()
    assert expected_label in forecast_text, (
        f"Expected '{expected_label}' in Cash Flow Forecast table, got:\n{forecast_text[:400]}"
    )


@when(
    'the user saves company letterhead settings for "{company_name}" with TRN "{trn}" and IBAN "{iban}"'
)
def step_save_company_settings(
    context,
    company_name: str,
    trn: str,
    iban: str,
) -> None:
    context.created_resources.append(("settings", "bookkeeping_settings"))
    context.reports_page.save_company_settings(
        company_name=company_name,
        company_address="Dubai Internet City, Building 3, UAE",
        company_trn=trn,
        iban=iban,
    )


@when(
    'the user saves UAE tax settings for company type "{company_type}" with Small Business Relief enabled'
)
def step_save_tax_settings(context, company_type: str) -> None:
    context.created_resources.append(("settings", "bookkeeping_settings"))
    context.reports_page.save_tax_settings(
        company_type=company_type,
        small_business_relief=True,
    )


@when('the user adds or updates the currency exchange rate for "{code}" to "{rate}" AED')
def step_add_currency_rate(context, code: str, rate: str) -> None:
    context.created_resources.append(("currency", code))
    context.reports_page.add_or_update_currency_rate(code=code, rate=rate)


@then('the Currency Exchange Rates table should list "{code}" with rate "{expected_rate_prefix}"')
def step_verify_currency_rate(
    context,
    code: str,
    expected_rate_prefix: str,
) -> None:
    table_text = context.reports_page.get_currency_rates_table_text()
    assert code in table_text and expected_rate_prefix in table_text, (
        f"Expected currency '{code}' with rate '{expected_rate_prefix}' in table, got:\n{table_text}"
    )


@then('the System Audit Trail should contain a "{action_name}" entry for "{detail_text}"')
def step_verify_audit_log_entry(
    context,
    action_name: str,
    detail_text: str,
) -> None:
    audit_text = context.reports_page.get_audit_log_text()
    assert action_name in audit_text and detail_text in audit_text, (
        f"Expected '{action_name}' and '{detail_text}' in Audit Log, got:\n{audit_text[:500]}"
    )
