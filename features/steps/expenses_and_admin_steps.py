"""Step definitions for Direct Expenses (`#view-expense`), Deferred Revenue (`2150`), Legal Modals, Plan Gating, and `/admin`."""

from __future__ import annotations

from behave import then, when


# --- Direct Expenses (`#view-expense`) ---


@when(
    'the user records a direct expense for payee "{payee}" of "{amount}" AED on "{account}" paid from "{paid_from}" in "{emirate}" with "{vat_treatment}" VAT'
)
def step_record_direct_expense(
    context,
    payee: str,
    amount: str,
    account: str,
    paid_from: str,
    emirate: str,
    vat_treatment: str,
) -> None:
    unique_payee = f"{payee} {context.scenario_uid}"
    context.last_expense_payee = unique_payee
    exp_num = context.expenses_admin_page.record_direct_expense(
        expense_date="2026-10-15",
        payee=unique_payee,
        description=f"Direct spend {context.scenario_uid}",
        account=account,
        paid_from=paid_from,
        emirate=emirate,
        vat_treatment=vat_treatment,
        amount_excl_vat=amount,
        apply_vat=(vat_treatment == "standard"),
    )
    context.last_expense_id = exp_num
    context.created_resources.append(("expense", exp_num))
    context.created_resources.append(("expense", unique_payee))


@then(
    'the Expense History table should list payee "{payee}" with VAT "{expected_vat}" and total "{expected_total}"'
)
def step_verify_expense_history_row(
    context,
    payee: str,
    expected_vat: str,
    expected_total: str,
) -> None:
    unique_payee = getattr(context, "last_expense_payee", payee)
    summary = context.expenses_admin_page.get_expense_history_summary()
    body = summary["body"]
    assert unique_payee in body, f"Expected payee '{unique_payee}' in Expense History, got:\n{body[:500]}"
    assert expected_vat in body and expected_total in body, (
        f"Expected VAT '{expected_vat}' and total '{expected_total}' in Expense History, got:\n{body[:500]}"
    )


@when('the user edits the last recorded expense amount to "{new_amount}" AED with 5% VAT')
def step_edit_last_direct_expense(context, new_amount: str) -> None:
    context.expenses_admin_page.edit_direct_expense_amount(
        context.last_expense_id, new_amount, apply_vat=True
    )


# --- Deferred Revenue (`2150`) Customer Invoice ---


@when(
    'the user fills a deferred-revenue customer invoice for "{customer_name}" over "{months}" months with item "{item_desc}" quantity "{qty}" at rate "{rate}" AED'
)
def step_fill_deferred_revenue_customer_invoice(
    context,
    customer_name: str,
    months: str,
    item_desc: str,
    qty: str,
    rate: str,
) -> None:
    unique_customer = f"{customer_name} {context.scenario_uid}"
    context.last_customer_name = unique_customer
    context.last_deferred_desc = f"Deferred Revenue - {unique_customer}"
    inv_num = context.transactions_page.fill_customer_invoice(
        invoice_date="2026-10-01",
        due_date="2026-10-31",
        customer_name=unique_customer,
        item_description=item_desc,
        qty=qty,
        rate=rate,
        vat_treatment="standard",
        revenue_account="4100 Service Revenue",
    )
    context.expenses_admin_page.enable_customer_invoice_deferred_revenue(months)
    context.last_invoice_num = inv_num
    context.created_resources.append(("ledger", inv_num))
    context.created_resources.append(("ledger", unique_customer))
    context.created_resources.append(("accrual", inv_num))


@then('the General Ledger should contain a "{expected_account}" entry for the deferred invoice')
def step_verify_deferred_revenue_in_ledger(context, expected_account: str) -> None:
    ledger_text = context.accounting_page.get_ledger_table_text()
    assert context.last_invoice_num in ledger_text and expected_account in ledger_text, (
        f"Expected invoice '{context.last_invoice_num}' with '{expected_account}' in General Ledger, got:\n{ledger_text[:600]}"
    )


# --- Detailed VAT 201 Boxes (`1a`, `1b`, `3`, `4`, `5`) ---


@when(
    'the user posts a standard-rated sales invoice in "{emirate}" for "{customer_name}" of "{rate}" AED'
)
def step_post_emirate_sales_invoice(
    context,
    emirate: str,
    customer_name: str,
    rate: str,
) -> None:
    context.base_page.navigate_to_view("Sales Invoices")
    unique_customer = f"{customer_name} {context.scenario_uid}"
    inv_num = context.transactions_page.fill_customer_invoice(
        invoice_date="2026-10-05",
        due_date="2026-11-05",
        customer_name=unique_customer,
        item_description=f"{emirate} Advisory Service",
        qty="1",
        rate=rate,
        vat_treatment="standard",
    )
    context.expenses_admin_page.set_customer_invoice_emirate(emirate)
    context.transactions_page.submit_customer_invoice()
    context.created_resources.append(("ledger", inv_num))
    context.created_resources.append(("ledger", unique_customer))


@then(
    'the VAT 201 return should show positive output VAT in Box 1a (Abu Dhabi) and Box 1b (Dubai) and positive Box 3 Reverse Charge'
)
def step_verify_vat201_emirate_and_rcm_boxes(context) -> None:
    vat = context.reports_page.get_vat_return_summary()
    for key in ("box1a", "box1b", "box3"):
        val = float(vat[key].replace(",", "") or 0)
        assert val > 0, f"Expected VAT 201 '{key}' > 0, got '{vat[key]}'"


# --- Welcome Legal Modals, Plan Gating & Super-Admin Console (`/admin`) ---


@when('the visitor opens the "{legal_key}" legal modal on the Welcome page')
def step_open_welcome_legal_modal(context, legal_key: str) -> None:
    context.last_legal_modal = context.expenses_admin_page.open_welcome_legal_modal(legal_key)


@then('the legal modal should display title "{expected_title}" and mention "{expected_keyword}"')
def step_verify_welcome_legal_modal(
    context, expected_title: str, expected_keyword: str
) -> None:
    modal = getattr(context, "last_legal_modal", {})
    assert expected_title in modal.get("title", ""), (
        f"Expected legal modal title '{expected_title}', got '{modal.get('title')}'"
    )
    assert expected_keyword in modal.get("body", ""), (
        f"Expected legal modal body to mention '{expected_keyword}', got:\n{modal.get('body', '')[:400]}"
    )


@then('the "{view_label}" navigation item should be locked with a plan badge')
def step_verify_sidebar_view_locked(context, view_label: str) -> None:
    target_id = context.base_page.VIEW_TARGET_MAP[view_label]
    assert context.expenses_admin_page.is_sidebar_view_locked(target_id), (
        f"Expected sidebar item '{view_label}' ({target_id}) to have .is-locked and .lock-badge"
    )


@when("the customer submits a plan upgrade request from Settings")
def step_submit_customer_plan_upgrade_request(context) -> None:
    context.plan_card_text = (
        context.expenses_admin_page.request_customer_plan_upgrade_in_settings()
    )


@then('the Settings Subscription Plan card should display "{expected_badge}"')
def step_verify_plan_upgrade_request_badge(context, expected_badge: str) -> None:
    card_text = getattr(context, "plan_card_text", "")
    assert expected_badge in card_text, (
        f"Expected '{expected_badge}' in Subscription Plan card, got:\n{card_text}"
    )


@when(
    'the administrator signs in to the Super-Admin Console with email "{email}" and password "{password}"'
)
def step_sign_in_admin_console(context, email: str, password: str) -> None:
    context.expenses_admin_page.open_and_sign_in_to_admin_console(email, password)


@then(
    "the Super-Admin Console should display MRR metrics and list the registered company with a pending upgrade"
)
def step_verify_admin_console_lists_upgrade_request(context) -> None:
    summary = context.expenses_admin_page.get_admin_console_summary()
    assert "AED" in summary["mrr"], f"Expected AED MRR KPI in /admin, got '{summary['mrr']}'"
    assert context.registered_company_name in summary["table"], (
        f"Expected tenant '{context.registered_company_name}' in /admin table, got:\n{summary['table'][:500]}"
    )
    assert "Approve" in summary["table"], (
        f"Expected 'Approve' button for pending upgrade in /admin table, got:\n{summary['table'][:500]}"
    )


@when("the administrator approves the pending upgrade request for the registered company")
def step_admin_approves_upgrade(context) -> None:
    context.updated_admin_table = (
        context.expenses_admin_page.approve_upgrade_request_in_admin(
            context.registered_company_name
        )
    )


@then("the Super-Admin Console should show no pending upgrade request for the registered company")
def step_verify_admin_upgrade_approved(context) -> None:
    table_text = getattr(context, "updated_admin_table", "")
    assert context.registered_company_name in table_text, (
        f"Expected '{context.registered_company_name}' in updated /admin table"
    )
