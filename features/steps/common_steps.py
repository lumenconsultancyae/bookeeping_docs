"""Common step definitions shared across all Lumen Accounting Suite BDD scenarios."""

from __future__ import annotations

from behave import given, then, when


@given('the bookkeeping application is open on the "{view_label}" view')
def step_open_application_on_view(context, view_label: str) -> None:
    context.base_page.open_application()
    if view_label != "Dashboard":
        context.base_page.navigate_to_view(view_label)


@when('the user navigates to the "{view_label}" view')
def step_navigate_to_view(context, view_label: str) -> None:
    target_id = context.base_page.navigate_to_view(view_label)
    assert context.base_page.is_view_displayed(target_id), (
        f"Expected view '{target_id}' for '{view_label}' to be displayed"
    )


@when(
    'the user posts a balanced journal entry of "{amount}" AED from "{debit_account}" to "{credit_account}" dated "{entry_date}"'
)
def step_post_balanced_journal_entry(
    context,
    amount: str,
    debit_account: str,
    credit_account: str,
    entry_date: str,
) -> None:
    context.base_page.navigate_to_view("Journal Entries")
    ref = f"JE-{context.scenario_uid}"
    desc = f"BDD Entry {context.scenario_uid}"
    context.last_journal_ref = ref
    context.last_journal_desc = desc
    context.created_resources.append(("ledger", ref))
    context.created_resources.append(("ledger", desc))

    context.accounting_page.fill_journal_form(
        entry_date=entry_date,
        reference=ref,
        description=desc,
        debit_account=debit_account,
        credit_account=credit_account,
        amount=amount,
        vat_treatment="exempt",
        is_ct_add_back=False,
    )
    context.accounting_page.submit_journal_entry()


@then("the live DOM should contain no unresolved template placeholders")
def step_verify_dom_integrity(context) -> None:
    report = context.base_page.check_dom_integrity()
    assert not report["hasUnresolvedTemplate"], (
        f"Found unresolved template expressions in live DOM: {report}"
    )
    assert not report["duplicateIds"], (
        f"Found duplicate element IDs in live DOM: {report['duplicateIds']}"
    )
