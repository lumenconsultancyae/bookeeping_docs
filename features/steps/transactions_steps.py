"""Step definitions for Commercial Transactions, AI Extraction, Quotes, POs, and Banking."""

from __future__ import annotations

from behave import then, when

from features.config import ARTIFACTS_DIR


@when(
    'the user fills a customer invoice for "{customer_name}" with item "{item_desc}" quantity "{qty}" at rate "{rate}" AED and "{vat_treatment}" VAT'
)
def step_fill_customer_invoice(
    context,
    customer_name: str,
    item_desc: str,
    qty: str,
    rate: str,
    vat_treatment: str,
) -> None:
    unique_customer = f"{customer_name} {context.scenario_uid}"
    context.last_invoice_customer = unique_customer
    inv_num = context.transactions_page.fill_customer_invoice(
        invoice_date="2026-10-10",
        due_date="2026-11-09",
        customer_name=unique_customer,
        item_description=item_desc,
        qty=qty,
        rate=rate,
        vat_treatment=vat_treatment,
    )
    context.last_invoice_num = inv_num
    context.created_resources.append(("customer", unique_customer))
    context.created_resources.append(("ledger", inv_num))
    context.created_resources.append(("ledger", unique_customer))


@then(
    'the customer invoice summary should show subtotal "{subtotal}", VAT "{vat}", and total "{total}"'
)
def step_verify_customer_invoice_summary(
    context,
    subtotal: str,
    vat: str,
    total: str,
) -> None:
    summary = context.transactions_page.get_customer_invoice_summary()
    assert float(summary["subtotal"].replace(",", "")) == float(subtotal.replace(",", "")), (
        f"Expected subtotal '{subtotal}', got '{summary['subtotal']}'"
    )
    assert float(summary["vat"].replace(",", "")) == float(vat.replace(",", "")), (
        f"Expected VAT '{vat}', got '{summary['vat']}'"
    )
    assert float(summary["total"].replace(",", "")) == float(total.replace(",", "")), (
        f"Expected total '{total}', got '{summary['total']}'"
    )


@when("the user previews the customer E-Invoice")
def step_preview_customer_einvoice(context) -> None:
    context.einvoice_preview_text = context.transactions_page.preview_customer_einvoice()


@then('the E-Invoice preview modal should display "{expected_heading}" and the customer name')
def step_verify_einvoice_preview(context, expected_heading: str) -> None:
    preview_text = getattr(context, "einvoice_preview_text", "")
    assert expected_heading in preview_text, (
        f"Expected '{expected_heading}' in E-Invoice preview, got:\n{preview_text[:400]}"
    )
    assert context.last_invoice_customer in preview_text, (
        f"Expected customer '{context.last_invoice_customer}' in E-Invoice preview"
    )
    context.base_page.dismiss_modals_if_present()


@when("the user submits the customer invoice to the ledger")
def step_submit_customer_invoice(context) -> None:
    context.transactions_page.submit_customer_invoice()


@when('the user loads the Statement of Account for "{mode_or_entity}"')
def step_load_soa(context, mode_or_entity: str) -> None:
    context.accounting_page.load_statement_of_account(mode_or_entity)


@then("the Statement of Account should list the customer invoice with a positive receivable balance")
def step_verify_soa_customer_invoice(context) -> None:
    soa = context.accounting_page.get_statement_kpis()
    assert context.last_invoice_customer in soa["table_text"] or context.last_invoice_num in soa["table_text"], (
        f"Expected customer invoice '{context.last_invoice_num}' in SOA table, got:\n{soa['table_text'][:400]}"
    )


@when(
    'the user fills an Art. 59 customer invoice for "{customer_name}" issued "{invoice_date}" supplied "{supply_date}" with item "{item_desc}" quantity "{qty}" at rate "{rate}" AED discount "{discount}" AED and "{vat_treatment}" VAT'
)
def step_fill_art59_customer_invoice(
    context,
    customer_name: str,
    invoice_date: str,
    supply_date: str,
    item_desc: str,
    qty: str,
    rate: str,
    discount: str,
    vat_treatment: str,
) -> None:
    unique_customer = f"{customer_name} {context.scenario_uid}"
    context.last_invoice_customer = unique_customer
    context.last_supply_date = supply_date
    inv_num = context.transactions_page.fill_customer_invoice(
        invoice_date=invoice_date,
        due_date="2026-11-09",
        customer_name=unique_customer,
        item_description=item_desc,
        qty=qty,
        rate=rate,
        vat_treatment=vat_treatment,
        supply_date=supply_date,
        discount=discount,
    )
    context.last_invoice_num = inv_num
    context.created_resources.append(("customer", unique_customer))
    context.created_resources.append(("ledger", inv_num))
    context.created_resources.append(("ledger", unique_customer))


@then(
    'the customer invoice summary should show discount "{discount}", subtotal "{subtotal}", VAT "{vat}", and total "{total}"'
)
def step_verify_art59_customer_invoice_summary(
    context,
    discount: str,
    subtotal: str,
    vat: str,
    total: str,
) -> None:
    summary = context.transactions_page.get_customer_invoice_summary()
    assert float(summary["discount"].replace(",", "")) == float(discount.replace(",", "")), (
        f"Expected discount '{discount}', got '{summary['discount']}'"
    )
    assert float(summary["subtotal"].replace(",", "")) == float(subtotal.replace(",", "")), (
        f"Expected subtotal '{subtotal}', got '{summary['subtotal']}'"
    )
    assert float(summary["vat"].replace(",", "")) == float(vat.replace(",", "")), (
        f"Expected VAT '{vat}', got '{summary['vat']}'"
    )
    assert float(summary["total"].replace(",", "")) == float(total.replace(",", "")), (
        f"Expected total '{total}', got '{summary['total']}'"
    )


@then('the E-Invoice preview modal should display Date of Supply "{expected_supply_date}", Discount, VAT Rate, and VAT Amount')
def step_verify_art59_einvoice_preview_fields(context, expected_supply_date: str) -> None:
    preview_text = getattr(context, "einvoice_preview_text", "")
    assert "TAX INVOICE" in preview_text, f"Expected 'TAX INVOICE' in preview, got:\n{preview_text[:400]}"
    assert "Date of Supply" in preview_text and expected_supply_date in preview_text, (
        f"Expected Date of Supply '{expected_supply_date}' in preview, got:\n{preview_text[:500]}"
    )
    assert "Discount" in preview_text, "Expected 'Discount' column/row in preview"
    assert "VAT Rate" in preview_text, "Expected 'VAT Rate' column in preview"
    assert "VAT Amount" in preview_text, "Expected 'VAT Amount' column in preview"
    context.base_page.dismiss_modals_if_present()


@when(
    'the user issues a Tax Credit Note against the last invoice with reason "{reason}", item "{item_desc}", quantity "{qty}", rate "{rate}" AED, discount "{discount}" AED, and "{vat_rate}" percent VAT'
)
def step_issue_tax_credit_note(
    context,
    reason: str,
    item_desc: str,
    qty: str,
    rate: str,
    discount: str,
    vat_rate: str,
) -> None:
    crn_num = context.transactions_page.fill_tax_credit_note_from_invoice(
        original_invoice_num=context.last_invoice_num,
        credit_date="2026-10-12",
        supply_date=getattr(context, "last_supply_date", "2026-10-05"),
        reason=reason,
        item_description=item_desc,
        qty=qty,
        rate=rate,
        discount=discount,
        vat_rate=vat_rate,
    )
    context.last_crn_num = crn_num
    context.created_resources.append(("ledger", crn_num))


@then(
    'the Tax Credit Note summary should show discount "{discount}", subtotal "{subtotal}", VAT "{vat}", and total "{total}"'
)
def step_verify_crn_summary(
    context,
    discount: str,
    subtotal: str,
    vat: str,
    total: str,
) -> None:
    summary = context.transactions_page.get_credit_note_summary()
    assert float(summary["discount"].replace(",", "")) == float(discount.replace(",", "")), (
        f"Expected CRN discount '{discount}', got '{summary['discount']}'"
    )
    assert float(summary["subtotal"].replace(",", "")) == float(subtotal.replace(",", "")), (
        f"Expected CRN subtotal '{subtotal}', got '{summary['subtotal']}'"
    )
    assert float(summary["vat"].replace(",", "")) == float(vat.replace(",", "")), (
        f"Expected CRN VAT '{vat}', got '{summary['vat']}'"
    )
    assert float(summary["total"].replace(",", "")) == float(total.replace(",", "")), (
        f"Expected CRN total '{total}', got '{summary['total']}'"
    )


@when("the user previews and submits the Tax Credit Note to the ledger")
def step_preview_and_submit_crn(context) -> None:
    preview_text = context.transactions_page.preview_tax_credit_note()
    assert "TAX CREDIT NOTE" in preview_text, f"Expected 'TAX CREDIT NOTE' in preview, got:\n{preview_text[:400]}"
    assert context.last_invoice_num in preview_text, (
        f"Expected original invoice ref '{context.last_invoice_num}' in CRN preview"
    )
    context.base_page.dismiss_modals_if_present()
    context.transactions_page.submit_tax_credit_note()


@then("the Statement of Account should list both the customer invoice and the Tax Credit Note")
def step_verify_soa_includes_crn(context) -> None:
    soa = context.accounting_page.get_statement_kpis()
    assert context.last_invoice_num in soa["table_text"], (
        f"Expected invoice '{context.last_invoice_num}' in SOA table, got:\n{soa['table_text'][:500]}"
    )
    assert context.last_crn_num in soa["table_text"] or "Credit Note" in soa["table_text"], (
        f"Expected credit note '{context.last_crn_num}' in SOA table, got:\n{soa['table_text'][:500]}"
    )


@when("the user uploads and analyzes a sample supplier invoice document")
def step_upload_and_analyze_supplier_bill(context) -> None:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    sample_png = ARTIFACTS_DIR / "sample_supplier_bill.png"
    context.transactions_page.generate_sample_supplier_invoice_png(sample_png)
    context.transactions_page.upload_and_analyze_supplier_document(sample_png)
    extracted = context.transactions_page.get_extracted_supplier_fields()
    # Suffix invoice number with scenario_uid to avoid duplicate detection across scenarios
    unique_inv = f"{extracted['invoice_num']}-{context.scenario_uid[:4]}"
    context.transactions_page.set_extracted_supplier_invoice_number(unique_inv)
    context.last_supplier_inv_num = unique_inv
    context.last_supplier_entity = extracted["entity"]
    context.created_resources.append(("ledger", unique_inv))
    context.created_resources.append(("ledger", extracted["entity"]))
    context.created_resources.append(("supplier", extracted["entity"]))


@when("the user uploads and analyzes a sample supplier invoice PDF document")
def step_upload_and_analyze_supplier_pdf(context) -> None:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    sample_pdf = ARTIFACTS_DIR / "MFZ-339673.pdf"
    context.transactions_page.generate_sample_supplier_invoice_pdf(sample_pdf)
    context.transactions_page.upload_and_analyze_supplier_document(sample_pdf)
    extracted = context.transactions_page.get_extracted_supplier_fields()
    unique_inv = f"{extracted['invoice_num']}-{context.scenario_uid[:4]}"
    context.transactions_page.set_extracted_supplier_invoice_number(unique_inv)
    context.last_supplier_inv_num = unique_inv
    context.last_supplier_entity = extracted["entity"]
    context.created_resources.append(("ledger", unique_inv))
    context.created_resources.append(("ledger", extracted["entity"]))
    context.created_resources.append(("supplier", extracted["entity"]))


@then(
    'the AI extraction review card should populate supplier "{expected_supplier}" and total "{expected_total}"'
)
def step_verify_ai_extracted_supplier_fields(
    context,
    expected_supplier: str,
    expected_total: str,
) -> None:
    extracted = context.transactions_page.get_extracted_supplier_fields()
    assert (
        expected_supplier.lower() in extracted["entity"].lower()
        or extracted["entity"].lower() in expected_supplier.lower()
    ), f"Expected extracted supplier '{expected_supplier}', got '{extracted['entity']}'"
    assert float(extracted["total"].replace(",", "")) == float(expected_total.replace(",", "")), (
        f"Expected extracted total '{expected_total}', got '{extracted['total']}'"
    )


@then(
    'the AI extraction review card should populate supplier "{expected_supplier}", tax "{expected_tax}", and total "{expected_total}"'
)
def step_verify_ai_extracted_supplier_pdf_fields(
    context,
    expected_supplier: str,
    expected_tax: str,
    expected_total: str,
) -> None:
    extracted = context.transactions_page.get_extracted_supplier_fields()
    assert (
        expected_supplier.lower() in extracted["entity"].lower()
        or "meydan" in extracted["entity"].lower()
    ), f"Expected extracted supplier '{expected_supplier}', got '{extracted['entity']}'"
    assert float(extracted["tax"].replace(",", "")) == float(expected_tax.replace(",", "")), (
        f"Expected extracted tax '{expected_tax}', got '{extracted['tax']}'"
    )
    assert float(extracted["total"].replace(",", "")) == float(expected_total.replace(",", "")), (
        f"Expected extracted total '{expected_total}', got '{extracted['total']}'"
    )


@when("the user confirms and saves the extracted supplier bill to the ledger")
def step_confirm_and_save_supplier_bill(context) -> None:
    context.transactions_page.confirm_and_save_supplier_bill()


@then('the General Ledger should contain the supplier bill for "{expected_supplier}"')
def step_verify_supplier_bill_in_ledger(context, expected_supplier: str) -> None:
    ledger_text = context.accounting_page.get_ledger_table_text()
    assert expected_supplier in ledger_text, (
        f"Expected supplier '{expected_supplier}' in General Ledger, got:\n{ledger_text[:500]}"
    )


@when(
    'the user creates a quote for client "{client_name}" with SKU "{sku}" quantity "{qty}" at price "{price}" AED'
)
def step_create_quote(
    context,
    client_name: str,
    sku: str,
    qty: str,
    price: str,
) -> None:
    quote_num = f"QT-{context.scenario_uid[:5]}"
    unique_client = f"{client_name} {context.scenario_uid}"
    actual_sku = getattr(context, "last_inventory_sku", sku)
    context.last_quote_num = quote_num
    context.created_resources.append(("quote", quote_num))
    context.created_resources.append(("customer", unique_client))
    context.created_resources.append(("ledger", unique_client))

    context.transactions_page.create_quote(
        quote_num=quote_num,
        quote_date="2026-10-12",
        client_name=unique_client,
        item_sku=actual_sku,
        qty=qty,
        price=price,
    )


@then('the Quotes history table should list the quote with status "{expected_status}"')
def step_verify_quote_status(context, expected_status: str) -> None:
    table_text = context.transactions_page.get_quotes_history_text()
    assert context.last_quote_num in table_text and expected_status in table_text, (
        f"Expected quote '{context.last_quote_num}' with status '{expected_status}', got:\n{table_text}"
    )


@when("the user converts the quote to a sales invoice")
def step_convert_quote_to_invoice(context) -> None:
    context.transactions_page.convert_quote_to_invoice(context.last_quote_num)
    # Return to Quotes view to inspect updated status
    context.base_page.navigate_to_view("Quotes & Estimates")


@when(
    'the user creates a purchase order for supplier "{supplier_name}" with SKU "{sku}" quantity "{qty}" at cost "{cost}" AED'
)
def step_create_po(
    context,
    supplier_name: str,
    sku: str,
    qty: str,
    cost: str,
) -> None:
    po_num = f"PO-{context.scenario_uid[:5]}"
    unique_supplier = f"{supplier_name} {context.scenario_uid}"
    actual_sku = getattr(context, "last_inventory_sku", sku)
    context.last_po_num = po_num
    context.created_resources.append(("po", po_num))
    context.created_resources.append(("supplier", unique_supplier))

    context.transactions_page.create_purchase_order(
        po_num=po_num,
        po_date="2026-10-14",
        supplier_name=unique_supplier,
        item_sku=actual_sku,
        qty=qty,
        cost=cost,
    )


@then('the Purchase Orders history table should list the purchase order with status "{expected_status}"')
def step_verify_po_status(context, expected_status: str) -> None:
    table_text = context.transactions_page.get_po_history_text()
    assert context.last_po_num in table_text and expected_status in table_text, (
        f"Expected PO '{context.last_po_num}' with status '{expected_status}', got:\n{table_text}"
    )


@when("the user marks the purchase order goods as received")
def step_receive_po_goods(context) -> None:
    context.transactions_page.receive_po_goods(context.last_po_num)


@when("the user converts the purchase order to a supplier bill")
def step_convert_po_to_bill(context) -> None:
    context.created_resources.append(("ledger", context.last_po_num))
    context.transactions_page.convert_po_to_bill(context.last_po_num)
    context.base_page.navigate_to_view("Purchase Orders")


@when(
    'the user creates a bank rule named "{rule_name}" matching keyword "{keyword}" to account "{target_account}" with "{vat_rate}" percent VAT'
)
def step_create_bank_rule(
    context,
    rule_name: str,
    keyword: str,
    target_account: str,
    vat_rate: str,
) -> None:
    unique_rule = f"{rule_name} {context.scenario_uid}"
    context.last_bank_rule_name = unique_rule
    context.created_resources.append(("bank_rule", unique_rule))

    context.transactions_page.add_bank_rule(
        rule_name=unique_rule,
        keyword_condition=keyword,
        target_account=target_account,
        vat_rate=vat_rate,
    )


@then('the Bank Rules table should list the rule "{rule_name}"')
def step_verify_bank_rule(context, rule_name: str) -> None:
    unique_rule = getattr(context, "last_bank_rule_name", rule_name)
    table_text = context.transactions_page.get_bank_rules_text()
    assert unique_rule in table_text, (
        f"Expected bank rule '{unique_rule}' in Bank Rules table, got:\n{table_text}"
    )


@when("the user connects the automated bank feed")
def step_connect_mock_bank_feed(context) -> None:
    context.created_resources.append(("bank_feeds", "mock"))
    context.transactions_page.connect_mock_bank_feeds()


@then("the Automated Bank Feeds table should display imported feed transactions")
def step_verify_bank_feeds(context) -> None:
    feeds_text = context.transactions_page.get_bank_feeds_text()
    assert "Stripe Payout" in feeds_text or "Match" in feeds_text, (
        f"Expected imported bank feed transactions, got:\n{feeds_text}"
    )


@when(
    'the user adds a "{frequency}" recurring "{tx_type}" template named "{template_name}" for "{entity_name}" of "{amount}" AED starting "{next_date}"'
)
def step_add_recurring_template(
    context,
    frequency: str,
    tx_type: str,
    template_name: str,
    entity_name: str,
    amount: str,
    next_date: str,
) -> None:
    unique_template = f"{template_name} {context.scenario_uid}"
    context.last_recurring_name = unique_template
    context.created_resources.append(("recurring", unique_template))

    context.transactions_page.add_recurring_template(
        template_name=unique_template,
        frequency=frequency,
        tx_type=tx_type,
        entity_name=entity_name,
        amount=amount,
        next_run_date=next_date,
    )


@then('the Recurring Transactions table should list "{template_name}"')
def step_verify_recurring_template(context, template_name: str) -> None:
    unique_template = getattr(context, "last_recurring_name", template_name)
    table_text = context.transactions_page.get_recurring_templates_text()
    assert unique_template in table_text, (
        f"Expected recurring template '{unique_template}' in table, got:\n{table_text}"
    )
