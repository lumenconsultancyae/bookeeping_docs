"""BDD step definitions for Onboarding Demo, Managed Books tier, and Team RBAC enforcement."""

from __future__ import annotations

import json

from behave import then, when


@then('the Managed Books welcome tier should display "{amount}" AED with "{promo}"')
def step_verify_managed_books_tier(context, amount: str, promo: str) -> None:
    plans = context.base_page.get_welcome_pricing_plans()
    managed = next((c for c in plans if "Managed" in c["title"]), None)
    assert managed is not None, f"Expected Managed Books card in {plans}"
    assert amount in managed["amount"], f"Expected amount '{amount}' in {managed}"
    assert promo in managed["promo"], f"Expected promo '{promo}' in {managed}"


@when('the visitor starts onboarding registration for company "{prefix}" with password "{password}" on the "{plan_id}" plan')
def step_start_onboarding_registration(context, prefix: str, password: str, plan_id: str) -> None:
    bp = context.base_page
    uid = context.scenario_uid
    company = f"{prefix} {uid}"
    context.registered_company_name = company
    context.registered_email = f"onboard.{uid}@lumenconsultancy.net"
    bp.click_id(f"btnChoose-{plan_id}")
    bp.wait_until(lambda p: p.locator("#setupModal").is_visible())
    for eid, val in (
        ("setupCompanyName", company),
        ("setupEmail", context.registered_email),
        ("setupPhone", "50 987 6543"),
        ("setupPassword", password),
        ("setupPasswordConfirm", password),
    ):
        bp.fill_input(eid, val)
    bp.wait_until(lambda p: p.locator("#recaptchaStubBtn").is_visible())
    bp.click_id("recaptchaStubBtn")
    bp.wait_until(lambda _p: bp.evaluate_script("return Boolean(document.getElementById('setupHumanCheckBox')?.classList.contains('is-verified'));"))
    bp.evaluate_script("const t = document.getElementById('setupAcceptTerms'); if (t && !t.checked) { t.checked = true; t.dispatchEvent(new Event('change', {bubbles: true})); }")
    bp.click_id("btnSetupSubmit")
    bp.wait_until(lambda p: p.locator("#onboardingSettingsBanner").is_visible() and bp._is_document_ready())


@then("the application should display the Settings onboarding banner for the registered company")
def step_verify_settings_onboarding_banner(context) -> None:
    text = context.base_page.get_text_by_id("onboardingSettingsBanner")
    assert context.registered_company_name in text, f"Expected company '{context.registered_company_name}' in banner: {text}"


@when("the founder saves company details in Settings onboarding")
def step_save_settings_onboarding(context) -> None:
    bp = context.base_page
    bp.fill_input("companyPhone", "+971 50 987 6543")
    bp.click_id("btnSaveCompanySettings")
    bp.wait_until(lambda p: p.locator("#lumyWelcomeBackdrop").is_visible())


@then("the Lumy AI welcome dialog should greet the registered company on the Dashboard")
def step_verify_lumy_welcome_dialog(context) -> None:
    text = context.base_page.get_text_by_id("lumenAiAssistantCard")
    assert context.registered_company_name in text, f"Expected Lumy welcome greeting for '{context.registered_company_name}', got:\n{text}"


@when("the founder launches and advances the interactive product demo")
def step_launch_and_advance_demo(context) -> None:
    bp = context.base_page
    bp.click_id("btnLumyStartDemo")
    bp.wait_until(lambda p: p.locator("#lumenDemoOverlay").is_visible() and "Step 1 of" in p.locator("#lumenDemoOverlay").inner_text())
    bp.click_id("btnDemoNext")
    bp.wait_until(lambda p: "Step 2 of" in p.locator("#lumenDemoOverlay").inner_text())
    context.demo_step2_title = bp.get_text_by_id("lumenDemoTitle")
    bp.click_id("btnDemoSkip")


@then("the interactive product demo should dismiss cleanly after Step 2")
def step_verify_demo_dismissed(context) -> None:
    assert getattr(context, "demo_step2_title", ""), "Expected Step 2 title to be captured"
    context.base_page.wait_until(lambda p: p.locator("#lumenDemoOverlay").count() == 0)


@when('the admin invites a "{role}" teammate named "{name}" with password "{password}"')
def step_invite_teammate(context, role: str, name: str, password: str) -> None:
    bp = context.base_page
    email = f"viewer.{context.scenario_uid}@lumenconsultancy.net"
    context.invited_viewer_email = email
    context.invited_viewer_password = password
    bp.wait_until(lambda p: p.locator("#newTeamUserForm").is_visible())
    bp.fill_input("teamUserName", name)
    bp.fill_input("teamUserEmail", email)
    bp.fill_input("teamUserPassword", password)
    bp.evaluate_script(
        "const r = document.getElementById('teamUserRole'); if (r) { r.value = arguments[0]; r.dispatchEvent(new Event('change', {bubbles: true})); }"
        "const f = document.getElementById('newTeamUserForm'); if (f) f.requestSubmit();",
        role,
    )
    bp.wait_until(lambda p: email in p.locator("#teamUsersList").inner_text())


@when("the invited viewer signs in on the Welcome page")
def step_invited_viewer_signs_in(context) -> None:
    bp = context.base_page
    bp.submit_sign_in_on_welcome(context.invited_viewer_email, context.invited_viewer_password)
    bp.wait_until(lambda p: p.locator(".app-layout").is_visible() and bp._is_document_ready())


@then('the workspace should reflect role "{expected_role}" and reject POST /api/v1/state with HTTP 403')
def step_verify_viewer_role_and_http_403(context, expected_role: str) -> None:
    bp = context.base_page
    res = bp.evaluate_script(
        """
        return (async () => {
            const roleAttr = document.body ? document.body.getAttribute('data-user-role') : '';
            const acc = sessionStorage.getItem('lumen_current_account') || '';
            const sess = sessionStorage.getItem('lumen_session_token') || '';
            const resp = await fetch('/api/v1/state', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Lumen-Client': 'lumen-bookkeeping-web',
                    'X-Lumen-Account': acc,
                    'X-Lumen-Session': sess
                },
                body: JSON.stringify({ set: { 'profile:blocked::journal': '[]' } })
            });
            return { roleAttr, status: resp.status, body: await resp.text() };
        })();
        """
    )
    assert res["roleAttr"] == expected_role, f"Expected body[data-user-role]='{expected_role}', got {res}"
    assert res["status"] == 403, f"Expected HTTP 403 for viewer POST /api/v1/state, got {res}: {json.dumps(res)}"
    bp.evaluate_script("if (window.LumenProfiles?.signOut) window.LumenProfiles.signOut();")
