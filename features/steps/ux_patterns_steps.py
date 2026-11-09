"""Step definitions for professional interaction patterns (pagination, validation, dialogs, drawer)."""

from __future__ import annotations

from behave import given, then, when


def _uid_name(context, base: str) -> str:
    return f"{base} {context.scenario_uid}"


def _test_customer(context, number: str) -> str:
    return f"UX {context.scenario_uid} Customer {int(number):02d}"


# --- Arrangement ---

@given("the customer directory contains {count:d} test customers")
def step_seed_customers(context, count: int) -> None:
    names = [_test_customer(context, str(i)) for i in range(1, count + 1)]
    context.created_resources.extend(("customer", n) for n in names)
    context.ux_page.seed_customers(names)


@given('a test customer named "{name}" exists')
def step_seed_one_customer(context, name: str) -> None:
    full = _uid_name(context, name)
    context.created_resources.append(("customer", full))
    context.ux_page.seed_customers([full])


@given("the general ledger contains {count:d} test journal entries")
def step_seed_ledger(context, count: int) -> None:
    descriptions = [f"UX {context.scenario_uid} accrual {i:02d}" for i in range(1, count + 1)]
    context.created_resources.extend(("ledger", d) for d in descriptions)
    context.ux_page.seed_journal_entries(descriptions)


@given("the browser window is resized to a {width:d} px wide tablet viewport")
def step_resize_window(context, width: int) -> None:
    context.page.set_viewport_size({"width": width, "height": 1000})
    context.ux_page.wait_until(lambda _p: context.base_page.evaluate_script("return window.innerWidth <= 960;"))


# --- Paginated tables ---

@then('the "{tbody_id}" table should show {count:d} rows with a pager summary starting "{prefix}"')
def step_table_first_page(context, tbody_id: str, count: int, prefix: str) -> None:
    snap = context.ux_page.wait_until(lambda d: context.ux_page.table_snapshot(tbody_id))
    assert len(snap["rows"]) == count, f"Expected {count} visible rows, got {len(snap['rows'])}"
    assert snap["pagerVisible"] and snap["summary"].startswith(prefix), f"Unexpected pager: {snap}"


@when('the user moves to page "{page}" of the "{tbody_id}" table')
def step_go_to_page(context, page: str, tbody_id: str) -> None:
    context.ux_page.go_to_table_page(tbody_id, page)


@then('the "{tbody_id}" table should mark page "{page}" as current')
def step_current_page(context, tbody_id: str, page: str) -> None:
    snap = context.ux_page.table_snapshot(tbody_id)
    assert snap["current"] == page, f"Expected current page {page}, got {snap}"


@when('the user searches the "{tbody_id}" table for test customer "{number}"')
def step_search_table(context, tbody_id: str, number: str) -> None:
    context.ux_page.search_table(tbody_id, _test_customer(context, number))


@then('the "{tbody_id}" table should show exactly 1 visible row containing test customer "{number}"')
def step_single_row(context, tbody_id: str, number: str) -> None:
    expected = _test_customer(context, number)
    snap = context.ux_page.wait_until(
        lambda d: (s := context.ux_page.table_snapshot(tbody_id)) and len(s["rows"]) == 1 and s)
    assert expected in snap["rows"][0], f"Expected '{expected}' in {snap['rows']}"


@then('the "{tbody_id}" table should show a highlighted row containing "{name}"')
def step_highlighted_row(context, tbody_id: str, name: str) -> None:
    full = _uid_name(context, name)
    snap = context.ux_page.table_snapshot(tbody_id)
    assert any(full in r for r in snap["rows"]), f"'{full}' not visible on the current page: {snap['rows']}"
    assert any(full in r for r in snap["highlighted"]), f"'{full}' should be highlighted: {snap['highlighted']}"


@then('the "{tbody_id}" table should still contain "{name}"')
def step_table_contains(context, tbody_id: str, name: str) -> None:
    full = _uid_name(context, name)
    assert any(full in r for r in context.ux_page.table_snapshot(tbody_id)["rows"]), f"'{full}' missing"


@then('the "{tbody_id}" table should not contain "{name}"')
def step_table_not_contains(context, tbody_id: str, name: str) -> None:
    full = _uid_name(context, name)
    context.ux_page.wait_until(
        lambda d: not any(full in r for r in context.ux_page.table_snapshot(tbody_id)["rows"]))


@then("the workspace should not need to scroll more than {ratio:g} screen heights")
def step_scroll_ratio(context, ratio: float) -> None:
    actual = context.ux_page.workspace_scroll_ratio()
    assert actual <= ratio, f"Workspace is {actual:.2f} screen heights tall (limit {ratio})"


# --- Inline validation ---

@when('the user submits the customer form with an empty name and TRN "{trn}"')
def step_submit_invalid_customer(context, trn: str) -> None:
    context.ux_page.submit_customer_form("", trn)


@then('the field "{field_id}" should show the inline error "{message}"')
def step_inline_error(context, field_id: str, message: str) -> None:
    actual = context.ux_page.inline_error(field_id)
    assert actual == message, f"Expected inline error '{message}', got '{actual}'"


@then("no notification should be displayed")
def step_no_toast(context) -> None:
    assert context.ux_page.visible_toast_count() == 0, "A toast was shown for an invalid form"


@when('the user corrects the customer form with test name "{name}" and TRN "{trn}" and submits')
def step_submit_valid_customer(context, name: str, trn: str) -> None:
    full = _uid_name(context, name)
    context.created_resources.append(("customer", full))
    context.ux_page.submit_customer_form(full, trn)


# --- Dialogs & toasts ---

@when('the user clicks Delete for test customer "{name}"')
def step_click_delete(context, name: str) -> None:
    context.ux_page.click_row_action("dirCustBody", _uid_name(context, name), "Delete")


@then('a danger confirmation dialog titled "{title}" should mention "{name}"')
def step_danger_dialog(context, title: str, name: str) -> None:
    dialog = context.ux_page.open_dialog()
    assert dialog["role"] == "alertdialog" and dialog["danger"], f"Unexpected dialog: {dialog}"
    assert dialog["title"] == title and _uid_name(context, name) in dialog["message"], f"Unexpected dialog: {dialog}"


@when("the user cancels the confirmation dialog")
def step_cancel_dialog(context) -> None:
    context.ux_page.answer_dialog(confirm=False)


@when("the user confirms the confirmation dialog")
def step_confirm_dialog(context) -> None:
    context.ux_page.answer_dialog(confirm=True)


@then('a "{toast_type}" notification containing "{text}" should be displayed')
def step_toast(context, toast_type: str, text: str) -> None:
    toast = context.ux_page.latest_toast()
    assert toast["type"] == toast_type and text in toast["text"], f"Unexpected toast: {toast}"


# --- Responsive drawer ---

@then("the sidebar should be hidden off-canvas with the menu button reporting it collapsed")
def step_drawer_closed(context) -> None:
    state = context.ux_page.wait_until(lambda d: (s := context.ux_page.drawer_state()) and s["sidebarRight"] <= 1 and s)
    assert state["expanded"] == "false" and not state["open"], f"Unexpected drawer state: {state}"


@when("the user opens the navigation drawer")
def step_open_drawer(context) -> None:
    context.ux_page.click_id("btnSidebarToggle")


@then("the sidebar drawer should be visible above a backdrop")
def step_drawer_open(context) -> None:
    state = context.ux_page.wait_until(lambda d: (s := context.ux_page.drawer_state()) and s["sidebarLeft"] >= 0 and s["open"] and s)
    assert state["backdrop"] and state["expanded"] == "true", f"Unexpected drawer state: {state}"


@when('the user picks "{view_label}" from the navigation drawer')
def step_pick_from_drawer(context, view_label: str) -> None:
    context.ux_page.navigate_to_view(view_label)


@then('the "{view_id}" view should be displayed with the drawer closed')
def step_view_and_drawer_closed(context, view_id: str) -> None:
    assert context.ux_page.is_view_displayed(view_id)
    context.ux_page.wait_until(lambda d: not context.ux_page.drawer_state()["open"])


@then('the React SPA root should be mounted with active route "{route_id}"')
def step_react_root_mounted(context, route_id: str) -> None:
    state = context.ux_page.wait_until(
        lambda d: (s := context.ux_page.react_spa_state()) and s["hasRoot"] and s["activeView"] == route_id and not s["isUnknownRoute"] and s
    )
    assert state["reactVersion"].startswith("18."), f"Unexpected React state: {state}"


@when('the user navigates to route hash "{route_id}"')
def step_navigate_route_hash(context, route_id: str) -> None:
    context.ux_page.navigate_hash(route_id)


@then('the contextual NotFound fallback should be visible for route "{route_id}"')
def step_not_found_visible(context, route_id: str) -> None:
    state = context.ux_page.wait_until(
        lambda d: (s := context.ux_page.react_spa_state()) and s["isUnknownRoute"] and s["notFoundVisible"] and s
    )
    assert route_id in state["notFoundText"], f"Expected '{route_id}' in NotFound fallback: {state}"


@when("the user clicks Return to Dashboard on the NotFound fallback")
def step_click_return_dashboard(context) -> None:
    context.ux_page.click_id("btnReturnDashboard")
