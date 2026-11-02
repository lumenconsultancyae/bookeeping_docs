"""Step definitions for Customers, Suppliers, Inventory, Stock Ledger, and Cheque Registry."""

from __future__ import annotations

from behave import given, then, when


@when(
    'the user registers a "{contact_type}" named "{entity_name}" with TRN "{trn}" and payment terms "{terms}" days'
)
def step_register_contact(
    context,
    contact_type: str,
    entity_name: str,
    trn: str,
    terms: str,
) -> None:
    unique_name = f"{entity_name} {context.scenario_uid}"
    context.last_contact_name = unique_name
    if contact_type.lower() == "customer":
        context.created_resources.append(("customer", unique_name))
        context.contacts_page.add_customer(
            name=unique_name,
            address="Business Bay, Dubai, UAE",
            phone="+971-4-555-0100",
            email=f"accounts.{context.scenario_uid}@example.ae",
            trn=trn,
            payment_terms=terms,
        )
    else:
        context.created_resources.append(("supplier", unique_name))
        context.contacts_page.add_supplier(
            name=unique_name,
            trn=trn,
            address="Jebel Ali Industrial Area, Dubai",
            phone="+971-4-555-0200",
            payment_terms=terms,
        )


@then('the "{directory_view}" directory should list the contact "{entity_name}" with TRN "{trn}"')
def step_verify_contact_in_directory(
    context,
    directory_view: str,
    entity_name: str,
    trn: str,
) -> None:
    unique_name = getattr(context, "last_contact_name", entity_name)
    if directory_view == "Customers":
        table_text = context.contacts_page.get_customer_directory_text()
    else:
        table_text = context.contacts_page.get_supplier_directory_text()
    assert unique_name in table_text and trn in table_text, (
        f"Expected '{unique_name}' and TRN '{trn}' in {directory_view} table, got:\n{table_text}"
    )


@when('the user enters an inventory unit cost of "{unit_cost}" AED and a markup of "{markup}" percent')
def step_enter_cost_and_markup(context, unit_cost: str, markup: str) -> None:
    context.last_unit_cost = unit_cost
    context.last_markup = markup
    context.calculated_price = context.contacts_page.set_inventory_cost_and_markup(
        unit_cost, markup
    )


@then('the calculated selling price field should be "{expected_price}"')
def step_verify_calculated_price(context, expected_price: str) -> None:
    actual = getattr(context, "calculated_price", "")
    assert float(actual) == float(expected_price), (
        f"Expected selling price '{expected_price}', got '{actual}'"
    )


@when(
    'the user saves the inventory item "{item_name}" with SKU "{sku}" and initial quantity "{qty}"'
)
def step_save_inventory_item(
    context,
    item_name: str,
    sku: str,
    qty: str,
) -> None:
    unique_name = f"{item_name} {context.scenario_uid}"
    unique_sku = f"{sku}-{context.scenario_uid[:4]}"
    context.last_inventory_name = unique_name
    context.last_inventory_sku = unique_sku
    context.created_resources.append(("inventory", unique_name))

    context.contacts_page.add_inventory_item(
        name=unique_name,
        sku=unique_sku,
        description="BDD Enterprise Hardware Item",
        unit_cost=getattr(context, "last_unit_cost", "200.00"),
        markup_pct=getattr(context, "last_markup", "35"),
        initial_qty=qty,
    )


@given('an inventory item "{item_name}" with SKU "{sku}" priced at "{price}" AED exists')
def step_given_inventory_item_priced(
    context,
    item_name: str,
    sku: str,
    price: str,
) -> None:
    context.base_page.navigate_to_view("Inventory Directory")
    unique_name = f"{item_name} {context.scenario_uid}"
    unique_sku = f"{sku}-{context.scenario_uid[:4]}"
    context.last_inventory_name = unique_name
    context.last_inventory_sku = unique_sku
    context.created_resources.append(("inventory", unique_name))

    context.contacts_page.add_inventory_item(
        name=unique_name,
        sku=unique_sku,
        description="Pre-seeded BDD Inventory Item",
        unit_cost=price,
        markup_pct="0",
        initial_qty="10",
    )


@given(
    'an inventory item "{item_name}" with SKU "{sku}" and initial quantity "{qty}" at unit cost "{cost}" AED exists'
)
def step_given_inventory_item_with_qty_and_cost(
    context,
    item_name: str,
    sku: str,
    qty: str,
    cost: str,
) -> None:
    context.base_page.navigate_to_view("Inventory Directory")
    unique_name = f"{item_name} {context.scenario_uid}"
    unique_sku = f"{sku}-{context.scenario_uid[:4]}"
    context.last_inventory_name = unique_name
    context.last_inventory_sku = unique_sku
    context.created_resources.append(("inventory", unique_name))

    context.contacts_page.add_inventory_item(
        name=unique_name,
        sku=unique_sku,
        description="Pre-seeded BDD PO Inventory Item",
        unit_cost=cost,
        markup_pct="25",
        initial_qty=qty,
    )


@then('the Inventory Directory should list "{item_name}" with quantity "{qty}"')
def step_verify_inventory_in_directory(context, item_name: str, qty: str) -> None:
    unique_name = getattr(context, "last_inventory_name", item_name)
    table_text = context.contacts_page.get_inventory_directory_text()
    assert unique_name in table_text and qty in table_text, (
        f"Expected '{unique_name}' with qty '{qty}' in Inventory Directory, got:\n{table_text}"
    )


@then(
    'the Stock Ledger should record an "{movement_type}" movement for "{item_name}" of "{qty_change}"'
)
@then(
    'the Stock Ledger should record a "{movement_type}" movement for "{item_name}" of "{qty_change}"'
)
def step_verify_stock_ledger_movement(
    context,
    movement_type: str,
    item_name: str,
    qty_change: str,
) -> None:
    unique_name = getattr(context, "last_inventory_name", item_name)
    ledger_text = context.contacts_page.get_stock_ledger_text()
    assert unique_name in ledger_text, (
        f"Expected product '{unique_name}' in Stock Ledger, got:\n{ledger_text}"
    )
    assert movement_type in ledger_text and qty_change in ledger_text, (
        f"Expected movement '{movement_type}' ({qty_change}) in Stock Ledger, got:\n{ledger_text}"
    )


@when(
    'the user registers cheque "{cheque_no}" for "{amount}" AED payable to "{supplier}" from "{bank_account}"'
)
def step_register_cheque(
    context,
    cheque_no: str,
    amount: str,
    supplier: str,
    bank_account: str,
) -> None:
    unique_cheque = f"{cheque_no}-{context.scenario_uid[:4]}"
    unique_supplier = f"{supplier} {context.scenario_uid}"
    context.last_cheque_no = unique_cheque
    context.last_cheque_supplier = unique_supplier
    context.created_resources.append(("cheque", unique_cheque))
    context.created_resources.append(("ledger", f"CHQ-{unique_cheque}"))

    context.contacts_page.register_cheque(
        cheque_number=unique_cheque,
        created_date="2026-10-01",
        cheque_date="2026-10-15",
        amount=amount,
        supplier_name=unique_supplier,
        bank_account=bank_account,
    )


@then('the Cheque Registry should list cheque "{cheque_no}" for supplier "{supplier}"')
def step_verify_cheque_in_registry(context, cheque_no: str, supplier: str) -> None:
    unique_cheque = getattr(context, "last_cheque_no", cheque_no)
    unique_supplier = getattr(context, "last_cheque_supplier", supplier)
    table_text = context.contacts_page.get_cheque_registry_text()
    assert unique_cheque in table_text and unique_supplier in table_text, (
        f"Expected cheque '{unique_cheque}' for '{unique_supplier}' in Cheque Registry, got:\n{table_text}"
    )
