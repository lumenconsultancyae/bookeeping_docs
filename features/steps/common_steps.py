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


@when("an unauthenticated visitor opens the application root")
def step_open_unauthenticated_root(context) -> None:
    context.redirected_url = context.base_page.open_unauthenticated_root()


@then('the browser should redirect to the "{expected_path}" entrypoint')
def step_verify_redirect_to_welcome(context, expected_path: str) -> None:
    current_url = context.page.url
    assert expected_path in current_url, (
        f"Expected browser URL to contain '{expected_path}', got '{current_url}'"
    )


@when('the visitor registers company "{company_prefix}" with password "{password}" on the "{plan_id}" plan')
def step_register_company_on_welcome(
    context, company_prefix: str, password: str, plan_id: str
) -> None:
    company_name = f"{company_prefix} {context.scenario_uid}"
    email = f"founder.{context.scenario_uid}@lumenconsultancy.net"
    context.registered_company_name = company_name
    context.registered_email = email
    context.registered_password = password
    context.base_page.register_account_on_welcome(
        company_name=company_name,
        email=email,
        password=password,
        plan_id=plan_id,
    )


@then("the topbar should display the signed-in user email")
def step_verify_topbar_user_email(context) -> None:
    displayed = context.base_page.get_topbar_user_name()
    assert displayed == context.registered_email, (
        f"Expected topbar user name '{context.registered_email}', got '{displayed}'"
    )


@when("the user signs out from the application topbar")
def step_sign_out_from_topbar(context) -> None:
    context.base_page.sign_out_from_topbar()


@when('the visitor attempts to sign in with password "{password}"')
def step_attempt_sign_in(context, password: str) -> None:
    context.base_page.submit_sign_in_on_welcome(context.registered_email, password)


@then('the sign-in modal should display the error "{expected_error}"')
def step_verify_sign_in_error(context, expected_error: str) -> None:
    actual = context.base_page.get_sign_in_error_text()
    assert actual == expected_error, (
        f"Expected sign-in error '{expected_error}', got '{actual}'"
    )


@when("the visitor toggles the sign-in password visibility button and checks Remember me")
def step_toggle_signin_password_and_remember_me(context) -> None:
    context.base_page.click_id("btnToggleSignInPassword")
    context.base_page.evaluate_script(
        "const cb = document.getElementById('signInRememberMe'); if (cb && !cb.checked) cb.click();"
    )


@then('the sign-in password input type should be "{expected_type}" and Remember me should be checked')
def step_verify_signin_password_type_and_remember(context, expected_type: str) -> None:
    state = context.base_page.evaluate_script(
        "return {"
        "  type: document.getElementById('signInPassword').type,"
        "  checked: Boolean(document.getElementById('signInRememberMe').checked),"
        "  hasEyeSvg: Boolean(document.querySelector('#btnToggleSignInPassword svg.icon-eye-off, #btnToggleSignInPassword svg.icon-eye'))"
        "};"
    )
    assert state["type"] == expected_type and state["checked"] is True and state["hasEyeSvg"] is True, (
        f"Expected signInPassword type '{expected_type}', Remember me checked, and SVG eye icon present, got {state}"
    )


@when('the visitor resets their locked password via the registered email to "{new_password}"')
def step_reset_locked_password_via_email(context, new_password: str) -> None:
    context.base_page.click_id("btnOpenResetFromLock")
    context.base_page.wait_until(
        lambda p: p.locator("#resetPasswordModal").is_visible()
    )
    context.base_page.fill_input("resetEmail", context.registered_email)
    context.base_page.click_id("btnSendResetCode")
    code = context.base_page.wait_until(
        lambda p: p.locator("#resetEmailSentNotice").get_attribute("data-reset-code")
    )
    assert code and len(code) == 6, f"Expected 6-digit reset code dispatched to email, got '{code}'"
    context.base_page.fill_input("resetCode", code)
    context.base_page.fill_input("resetNewPassword", new_password)
    context.base_page.fill_input("resetConfirmPassword", new_password)
    context.base_page.click_id("btnResetPasswordSubmit")
    context.base_page.wait_until(
        lambda p: p.locator("#signInModal").is_visible()
    )


@when("the user toggles the topbar language switcher")
def step_toggle_language_switcher(context) -> None:
    context.created_resources.append(("lang", "en"))
    context.base_page.toggle_language()


@then('the document language should be "{expected_lang}" with direction "{expected_dir}"')
def step_verify_document_lang_and_dir(context, expected_lang: str, expected_dir: str) -> None:
    lang, direction = context.base_page.get_document_lang_and_dir()
    assert lang == expected_lang and direction == expected_dir, (
        f"Expected html[lang='{expected_lang}'][dir='{expected_dir}'], got lang='{lang}', dir='{direction}'"
    )


@then('the welcome hero heading should contain "{expected_text}"')
def step_verify_welcome_hero_heading(context, expected_text: str) -> None:
    heading = context.base_page.get_welcome_hero_heading()
    assert expected_text in heading, (
        f"Expected welcome hero heading to contain '{expected_text}', got '{heading}'"
    )


@when('a verification screenshot "{screenshot_name}" is captured')
def step_capture_named_screenshot(context, screenshot_name: str) -> None:
    context.base_page.capture_step_screenshot(screenshot_name)


@then(
    'the welcome pricing plans should display Basic at "{basic_price}" AED and "{promo_text}" promotion on all tiers'
)
def step_verify_welcome_pricing_and_promo(
    context,
    basic_price: str,
    promo_text: str,
) -> None:
    info = context.base_page.get_welcome_pricing_plans()
    assert len(info) == 3, f"Expected 3 plan cards on /welcome, got {len(info)}: {info}"
    basic_card = next((c for c in info if "Basic" in c["title"]), None)
    assert basic_card and basic_card["amount"].strip() == basic_price, (
        f"Expected Basic plan price '{basic_price}', got {basic_card}"
    )
    for card in info:
        assert promo_text in card["promo"], f"Expected '{promo_text}' on tier '{card['title']}', got '{card['promo']}'"
