"""Step definitions for Chart of Accounts, Journal Entries, Accruals, and Period Locking."""

from __future__ import annotations

from behave import then, when


@when('the user adds a custom account with code "{code}" named "{name}" of type "{acc_type}"')
def step_add_custom_account(context, code: str, name: str, acc_type: str) -> None:
    unique_code = f"{code}{context.scenario_uid[:2]}"
    unique_name = f"{name} {context.scenario_uid}"
    context.custom_coa_code = unique_code
    context.custom_coa_name = unique_name
    context.created_resources.append(("coa", unique_code))
    context.accounting_page.add_custom_account(unique_code, unique_name, acc_type)


@then('the Chart of Accounts table should list the custom account "{name}"')
def step_verify_custom_account_in_coa(context, name: str) -> None:
    expected_name = getattr(context, "custom_coa_name", name)
    table_text = context.accounting_page.get_coa_table_text()
    assert expected_name in table_text, (
        f"Expected custom account '{expected_name}' in COA table, got:\n{table_text[:400]}"
    )


@when(
    'the user prepares a journal entry for "{amount}" AED debiting "{debit_account}" and crediting "{credit_account}" with "{vat_treatment}" VAT'
)
def step_prepare_journal_entry(
    context,
    amount: str,
    debit_account: str,
    credit_account: str,
    vat_treatment: str,
) -> None:
    ref = f"JE-{context.scenario_uid}"
    desc = f"Manual Journal {context.scenario_uid}"
    context.last_journal_ref = ref
    context.last_journal_desc = desc
    context.created_resources.append(("ledger", ref))
    context.created_resources.append(("ledger", desc))

    context.accounting_page.fill_journal_form(
        entry_date="2026-09-15",
        reference=ref,
        description=desc,
        debit_account=debit_account,
        credit_account=credit_account,
        amount=amount,
        vat_treatment=vat_treatment,
        is_ct_add_back=False,
    )


@when(
    'the user prepares a journal entry for "{amount}" AED debiting "{debit_account}" and crediting "{credit_account}" with "{vat_treatment}" VAT flagged as a Corporate Tax Add-Back'
)
def step_prepare_ct_addback_journal_entry(
    context,
    amount: str,
    debit_account: str,
    credit_account: str,
    vat_treatment: str,
) -> None:
    ref = f"JECT-{context.scenario_uid}"
    desc = f"CT AddBack Journal {context.scenario_uid}"
    context.last_journal_ref = ref
    context.last_journal_desc = desc
    context.created_resources.append(("ledger", ref))
    context.created_resources.append(("ledger", desc))

    context.accounting_page.fill_journal_form(
        entry_date="2026-09-20",
        reference=ref,
        description=desc,
        debit_account=debit_account,
        credit_account=credit_account,
        amount=amount,
        vat_treatment=vat_treatment,
        is_ct_add_back=True,
    )


@when("the user previews the journal posting")
def step_preview_journal(context) -> None:
    context.journal_preview_text = context.accounting_page.preview_journal_entry()


@then('the journal posting preview should include "{expected_account}"')
def step_verify_journal_preview(context, expected_account: str) -> None:
    preview = getattr(context, "journal_preview_text", "")
    assert expected_account in preview, (
        f"Expected '{expected_account}' in journal preview, got:\n{preview}"
    )


@when("the user submits the prepared journal entry")
def step_submit_prepared_journal(context) -> None:
    context.accounting_page.submit_journal_entry()


@then("the General Ledger should contain the posted journal entry")
def step_verify_journal_in_ledger(context) -> None:
    ledger_text = context.accounting_page.get_ledger_table_text()
    assert context.last_journal_desc in ledger_text or context.last_journal_ref in ledger_text, (
        f"Expected journal '{context.last_journal_desc}' in General Ledger, got:\n{ledger_text[:500]}"
    )


@when(
    'the user creates a prepaid accrual for "{desc}" of "{amount}" AED over "{months}" months starting "{start_date}"'
)
def step_create_prepaid_accrual(
    context,
    desc: str,
    amount: str,
    months: str,
    start_date: str,
) -> None:
    unique_desc = f"{desc} {context.scenario_uid}"
    context.last_accrual_desc = unique_desc
    context.created_resources.append(("accrual", unique_desc))
    context.created_resources.append(("ledger", unique_desc))

    context.accounting_page.add_accrual_schedule(
        start_date=start_date,
        description=unique_desc,
        debit_account="6400 Rent Expense",
        credit_account="1410 Prepaid Rent",
        total_amount=amount,
        life_months=months,
    )


@then(
    'the Accruals directory should list the schedule for "{desc}" with monthly amortization "{expected_monthly}"'
)
def step_verify_accrual_in_directory(
    context,
    desc: str,
    expected_monthly: str,
) -> None:
    unique_desc = getattr(context, "last_accrual_desc", desc)
    table_text = context.accounting_page.get_accruals_table_text()
    assert unique_desc in table_text, (
        f"Expected accrual '{unique_desc}' in Accruals table, got:\n{table_text}"
    )
    assert expected_monthly in table_text, (
        f"Expected monthly amortization '{expected_monthly}' in Accruals table, got:\n{table_text}"
    )


@then(
    'the accrual amortization schedule modal for "{desc}" should contain "{expected_count}" monthly installments'
)
def step_verify_accrual_schedule_modal(
    context,
    desc: str,
    expected_count: str,
) -> None:
    unique_desc = getattr(context, "last_accrual_desc", desc)
    schedule_text = context.accounting_page.open_accrual_schedule_modal(unique_desc)
    lines = [line for line in schedule_text.splitlines() if line.strip()]
    assert len(lines) == int(expected_count), (
        f"Expected {expected_count} schedule rows, got {len(lines)}:\n{schedule_text}"
    )
    context.base_page.dismiss_modals_if_present()


@when('the user locks the General Ledger up to "{close_date}"')
def step_lock_ledger(context, close_date: str) -> None:
    context.created_resources.append(("closed_date", close_date))
    context.lock_alert = context.accounting_page.lock_ledger_through_date(close_date)


@when("the user attempts to delete the locked journal entry from the General Ledger")
def step_attempt_delete_locked_entry(context) -> None:
    context.delete_alert = context.accounting_page.attempt_delete_ledger_entry_by_ref(
        context.last_journal_desc
    )


@then("the system should block the deletion with a closed period warning")
def step_verify_closed_period_warning(context) -> None:
    alert_msg = getattr(context, "delete_alert", "") or ""
    assert "closed period" in alert_msg.lower() or "cannot delete" in alert_msg.lower(), (
        f"Expected closed period warning alert, got '{alert_msg}'"
    )


@then("the General Ledger should still contain the locked journal entry")
def step_verify_locked_entry_remains(context) -> None:
    ledger_text = context.accounting_page.get_ledger_table_text()
    assert context.last_journal_desc in ledger_text, (
        f"Expected locked entry '{context.last_journal_desc}' to remain in General Ledger"
    )


@when("the user deletes the unlocked journal entry from the General Ledger")
def step_delete_unlocked_entry(context) -> None:
    context.delete_alert = context.accounting_page.attempt_delete_ledger_entry_by_ref(
        context.last_journal_desc
    )


@then("the General Ledger should not contain the deleted journal entry")
def step_verify_deleted_entry_removed(context) -> None:
    ledger_text = context.accounting_page.get_ledger_table_text()
    assert context.last_journal_desc not in ledger_text, (
        f"Expected deleted entry '{context.last_journal_desc}' to be removed from General Ledger, got:\n{ledger_text[:500]}"
    )


@when(
    'the user creates a usage-based accrual schedule for "{desc}" of "{amount}" AED debiting "{debit_account}" and crediting "{credit_account}" starting "{start_date}"'
)
def step_create_usage_accrual(
    context,
    desc: str,
    amount: str,
    debit_account: str,
    credit_account: str,
    start_date: str,
) -> None:
    unique_desc = f"{desc} {context.scenario_uid}"
    context.last_accrual_desc = unique_desc
    context.created_resources.append(("accrual", unique_desc))
    context.created_resources.append(("ledger", unique_desc))

    context.accounting_page.add_accrual_schedule(
        start_date=start_date,
        description=unique_desc,
        debit_account=debit_account,
        credit_account=credit_account,
        total_amount=amount,
        life_months="12",
        schedule_mode="usage",
    )


@when(
    'the user records a usage drawdown of "{usage_amount}" AED on "{desc}" dated "{usage_date}" with note "{usage_note}"'
)
def step_record_accrual_usage_drawdown(
    context,
    usage_amount: str,
    desc: str,
    usage_date: str,
    usage_note: str,
) -> None:
    unique_desc = getattr(context, "last_accrual_desc", desc)
    context.accounting_page.record_accrual_usage_drawdown(
        description=unique_desc,
        usage_date=usage_date,
        usage_amount=usage_amount,
        usage_note=usage_note,
    )


@then(
    'the Accruals directory should show "{desc}" with accumulated recognition "{expected_accumulated}" and net balance "{expected_net}"'
)
def step_verify_usage_accrual_balances(
    context,
    desc: str,
    expected_accumulated: str,
    expected_net: str,
) -> None:
    unique_desc = getattr(context, "last_accrual_desc", desc)
    table_text = context.accounting_page.get_accruals_table_text()
    assert unique_desc in table_text, (
        f"Expected usage accrual '{unique_desc}' in Accruals table, got:\n{table_text}"
    )
    assert expected_accumulated in table_text and expected_net in table_text, (
        f"Expected accumulated '{expected_accumulated}' and net balance '{expected_net}' in Accruals table, got:\n{table_text}"
    )

