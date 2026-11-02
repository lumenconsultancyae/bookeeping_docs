"""Page Object for Sales Invoices, Supplier Bills, Banking, Quotes, POs, and Recurring Transactions."""

from __future__ import annotations

import base64
from pathlib import Path
from selenium.webdriver.common.by import By

from features.pages.base_page import BasePage


class TransactionsPage(BasePage):
    """UI adapter for commercial transaction views (`#view-customer`, `#view-supplier`, `#view-bank`, `#view-quotes`, `#view-po`, `#view-recurring`)."""

    # --- Customer Sales Invoices (`#view-customer`) ---

    def fill_customer_invoice(
        self,
        invoice_date: str,
        due_date: str,
        customer_name: str,
        item_description: str,
        qty: str,
        rate: str,
        vat_treatment: str = "standard",
        revenue_account: str = "4100 Service Revenue",
    ) -> str:
        """Populate the Customer Sales Invoice form and return the generated `#custInvoiceNum`."""
        self.driver.execute_script("window.isVatApplicable = arguments[0] === 'standard';", vat_treatment)
        self.fill_input("custDate", invoice_date)
        self.fill_input("custDueDate", due_date)
        self.fill_input("custEntity", customer_name)
        self.select_by_value_or_text("custRevenueAccount", revenue_account)

        self.driver.execute_script(
            """
            const row = document.querySelector('#custLineItemsList .line-item-row');
            if (row) {
                const desc = row.querySelector('.item-desc');
                const qty = row.querySelector('.item-qty');
                const rate = row.querySelector('.item-rate');
                desc.value = arguments[0];
                desc.dispatchEvent(new Event('input', {bubbles: true}));
                qty.value = arguments[1];
                qty.dispatchEvent(new Event('input', {bubbles: true}));
                rate.value = arguments[2];
                rate.dispatchEvent(new Event('input', {bubbles: true}));
            }
            const radios = document.querySelectorAll('input[name="vatToggle"]');
            radios.forEach(r => {
                if (r.value === arguments[3]) {
                    r.checked = true;
                    r.dispatchEvent(new Event('change', {bubbles: true}));
                }
            });
            if (typeof window.calcCustTotals === 'function') window.calcCustTotals();
            """,
            item_description,
            str(qty),
            str(rate),
            vat_treatment,
        )
        return self.get_value_by_id("custInvoiceNum")

    def get_customer_invoice_summary(self) -> dict[str, str]:
        """Return the calculated subtotal, VAT, and total displayed on the invoice form."""
        return {
            "subtotal": self.get_text_by_id("custSubtotalDisplay"),
            "vat": self.get_text_by_id("custVatDisplay"),
            "total": self.get_text_by_id("custTotalDisplay"),
        }

    def preview_customer_einvoice(self) -> str:
        """Click `#previewInvoiceBtn` and return the rendered E-Invoice modal text."""
        self.click_id("previewInvoiceBtn")
        self.wait_until(lambda d: d.find_element(By.ID, "invoiceModal").is_displayed())
        return self.get_text_by_id("modalBody")

    def submit_customer_invoice(self) -> str | None:
        """Submit `#customerInvoiceForm`, post the entry, and return any alert text."""
        self.dismiss_modals_if_present()
        self.driver.execute_script(
            "document.getElementById('customerInvoiceForm').requestSubmit();"
        )
        alert_text = self.accept_alert_if_present(timeout=3.0)
        self.post_latest_ledger_entry()
        return alert_text

    # --- Supplier Bills AI Extraction (`#view-supplier`) ---

    def generate_sample_supplier_invoice_png(self, sample_file_path: Path) -> None:
        """Render a high-contrast Supplier Invoice PNG image via HTML5 canvas and save to `sample_file_path`."""
        b64_png = self.driver.execute_script(
            """
            const c = document.createElement('canvas');
            c.width = 800;
            c.height = 500;
            const ctx = c.getContext('2d');
            ctx.fillStyle = '#ffffff';
            ctx.fillRect(0, 0, 800, 500);
            ctx.fillStyle = '#0f172a';
            ctx.font = 'bold 28px sans-serif';
            ctx.fillText('TAX INVOICE / SUPPLIER BILL', 40, 60);
            ctx.font = '22px sans-serif';
            ctx.fillText('Supplier: Gulf Cloud Infrastructure LLC', 40, 120);
            ctx.fillText('TRN: 100998877665503', 40, 160);
            ctx.fillText('Address: Dubai Internet City, UAE', 40, 195);
            ctx.fillText('Invoice Number: SUP-AI-8001', 40, 230);
            ctx.fillText('Invoice Date: 2026-10-15', 40, 265);
            ctx.fillText('Item: Managed Cloud Compute Cluster | Qty: 1 | Unit Price: 2000.00 | Tax: 100.00 | Amount: 2000.00', 40, 320);
            ctx.fillText('Subtotal: 2000.00 AED', 40, 370);
            ctx.fillText('VAT (5%): 100.00 AED', 40, 410);
            ctx.font = 'bold 24px sans-serif';
            ctx.fillText('Total Amount: 2100.00 AED', 40, 460);
            return c.toDataURL('image/png').split(',')[1];
            """
        )
        sample_file_path.write_bytes(base64.b64decode(b64_png))

    def generate_sample_supplier_invoice_pdf(self, sample_pdf_path: Path) -> None:
        """Write the Meydan Free Zone PDF tax invoice (`MFZ-339673`) to `sample_pdf_path`."""
        uploaded_pdf = sample_pdf_path.resolve().parents[2] / ".user_uploaded" / "MFZ-339673 (1).pdf"
        if uploaded_pdf.is_file():
            sample_pdf_path.write_bytes(uploaded_pdf.read_bytes())
            return

        content_stream = (
            b"BT\n"
            b"/F1 16 Tf 40 750 Td (TAX INVOICE # MFZ - 339673) Tj\n"
            b"/F1 12 Tf 0 -25 Td (Supplier: Meydan Free Zone) Tj\n"
            b"0 -20 Td (TRN: 100027637600003) Tj\n"
            b"0 -20 Td (Invoice Date: 2026-06-23) Tj\n"
            b"0 -25 Td (1. License - New | Qty: 1 | Net Amount: 12125.00 | Tax: 0.00) Tj\n"
            b"0 -20 Td (2. Facility - Co-working shared desk - New | Qty: 1 | Net Amount: 357.14 | Tax: 17.86) Tj\n"
            b"0 -20 Td (3. Innovation Fee | Qty: 1 | Net Amount: 10.00 | Tax: 0.00) Tj\n"
            b"0 -20 Td (4. Knowledge Fee | Qty: 1 | Net Amount: 10.00 | Tax: 0.00) Tj\n"
            b"0 -25 Td (Subtotal: 12502.14 AED | VAT 5%: 17.86 AED | Total: 12520.00 AED) Tj\n"
            b"ET\n"
        )
        pdf_bytes = (
            b"%PDF-1.4\n"
            b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
            b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
            b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj\n"
            + f"4 0 obj << /Length {len(content_stream)} >> stream\n".encode("ascii")
            + content_stream
            + b"endstream endobj\n"
            b"5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n"
            b"xref\n0 6\n0000000000 65535 f \n"
            b"trailer << /Size 6 /Root 1 0 R >>\n%%EOF\n"
        )
        sample_pdf_path.write_bytes(pdf_bytes)

    def upload_and_analyze_supplier_document(self, sample_file_path: Path) -> None:
        """Upload a document to `#fileInput`, click `#processBtn`, and wait for `#resultCard`."""
        def _send_file(driver):
            file_input = driver.find_element(By.ID, "fileInput")
            file_input.send_keys(str(sample_file_path))
            return True

        self.wait_until(_send_file)
        self.wait_until(lambda d: d.find_element(By.ID, "processBtn").is_displayed())
        self.click_id("processBtn")
        self.wait_until(
            lambda d: d.find_element(By.ID, "resultCard").is_displayed(),
            timeout=90.0,
        )

    def set_extracted_supplier_invoice_number(self, invoice_num: str) -> None:
        """Set the extracted supplier invoice number in `#resInvoiceNum`."""
        self.fill_input("resInvoiceNum", invoice_num)

    def get_extracted_supplier_fields(self) -> dict[str, str]:
        """Return the AI-extracted fields from `#resultCard`."""
        return {
            "invoice_num": self.get_value_by_id("resInvoiceNum"),
            "date": self.get_value_by_id("resDate"),
            "entity": self.get_value_by_id("resEntity"),
            "trn": self.get_value_by_id("resTrn"),
            "subtotal": self.get_value_by_id("resSubtotal"),
            "tax": self.get_value_by_id("resTax"),
            "total": self.get_value_by_id("resTotal"),
        }

    def confirm_and_save_supplier_bill(self) -> str | None:
        """Click `#confirmSaveSupplierBtn`, accept any confirmation alert, and post the entry."""
        self.click_id("confirmSaveSupplierBtn")
        alert_text = self.accept_alert_if_present(timeout=3.0)
        self.post_latest_ledger_entry()
        return alert_text

    # --- Quotes & Estimates (`#view-quotes`) ---

    def create_quote(
        self,
        quote_num: str,
        quote_date: str,
        client_name: str,
        item_sku: str,
        qty: str,
        price: str,
    ) -> None:
        """Populate the Quote form, select an inventory SKU line item, and click `#saveQuoteBtn`."""
        self.fill_input("quoteNum", quote_num)
        self.fill_input("quoteDate", quote_date)
        self.fill_input("quoteClient", client_name)
        self.driver.execute_script(
            """
            const container = document.getElementById('quoteLineItems');
            if (container && typeof window.renderQuoteLineItem === 'function') {
                container.innerHTML = '';
                window.renderQuoteLineItem();
            }
            const row = document.querySelector('#quoteLineItems .form-group.inline');
            if (row) {
                const sel = row.querySelector('.quote-item-select');
                const qtyInput = row.querySelector('.quote-qty');
                const priceInput = row.querySelector('.quote-price');
                if (sel) {
                    sel.value = arguments[0];
                    sel.dispatchEvent(new Event('change', {bubbles: true}));
                }
                if (qtyInput) {
                    qtyInput.value = arguments[1];
                    qtyInput.dispatchEvent(new Event('input', {bubbles: true}));
                }
                if (priceInput) {
                    priceInput.value = arguments[2];
                    priceInput.dispatchEvent(new Event('input', {bubbles: true}));
                }
            }
            if (typeof window.updateQuoteTotal === 'function') window.updateQuoteTotal();
            """,
            item_sku,
            str(qty),
            str(price),
        )
        self.click_id("saveQuoteBtn")
        self.accept_alert_if_present(timeout=2.0)

    def convert_quote_to_invoice(self, quote_num: str) -> str | None:
        """Convert a saved quote to a sales invoice and accept the alert."""
        self.driver.execute_script(
            """
            const quotes = JSON.parse(localStorage.getItem('bookkeeping_quotes') || '[]');
            const found = quotes.find(q => q.quoteNum === arguments[0]);
            if (found && typeof window.convertQuoteToInvoice === 'function') {
                window.convertQuoteToInvoice(found.id);
            }
            """,
            quote_num,
        )
        return self.accept_alert_if_present(timeout=3.0)

    def get_quotes_history_text(self) -> str:
        """Return the text of `#quotesHistoryBody`."""
        self.driver.execute_script(
            "if (typeof window.renderQuotesHistory === 'function') window.renderQuotesHistory();"
        )
        return self.get_text_by_id("quotesHistoryBody")

    # --- Purchase Orders (`#view-po`) ---

    def create_purchase_order(
        self,
        po_num: str,
        po_date: str,
        supplier_name: str,
        item_sku: str,
        qty: str,
        cost: str,
    ) -> None:
        """Populate the Purchase Order form and click `#savePOBtn`."""
        self.fill_input("poNum", po_num)
        self.fill_input("poDate", po_date)
        self.fill_input("poSupplier", supplier_name)
        self.driver.execute_script(
            """
            const container = document.getElementById('poLineItems');
            if (container && typeof window.renderPOLineItem === 'function') {
                container.innerHTML = '';
                window.renderPOLineItem();
            }
            const row = document.querySelector('#poLineItems .form-group.inline');
            if (row) {
                const sel = row.querySelector('.po-item-select');
                const qtyInput = row.querySelector('.po-qty');
                const costInput = row.querySelector('.po-cost');
                if (sel) {
                    sel.value = arguments[0];
                    sel.dispatchEvent(new Event('change', {bubbles: true}));
                }
                if (qtyInput) {
                    qtyInput.value = arguments[1];
                    qtyInput.dispatchEvent(new Event('input', {bubbles: true}));
                }
                if (costInput) {
                    costInput.value = arguments[2];
                    costInput.dispatchEvent(new Event('input', {bubbles: true}));
                }
            }
            if (typeof window.updatePOTotal === 'function') window.updatePOTotal();
            """,
            item_sku,
            str(qty),
            str(cost),
        )
        self.click_id("savePOBtn")
        self.accept_alert_if_present(timeout=2.0)

    def receive_po_goods(self, po_num: str) -> str | None:
        """Trigger Goods Receipt (`receivePOGoods`) for `po_num` and accept the confirmation alert."""
        self.driver.execute_script(
            """
            const pos = JSON.parse(localStorage.getItem('bookkeeping_pos') || '[]');
            const found = pos.find(p => p.poNum === arguments[0]);
            if (found && typeof window.receivePOGoods === 'function') {
                window.receivePOGoods(found.id);
            }
            """,
            po_num,
        )
        return self.accept_alert_if_present(timeout=3.0)

    def convert_po_to_bill(self, po_num: str) -> str | None:
        """Perform 3-way match (`convertPOToBill`) for `po_num` and accept the confirmation alert."""
        self.driver.execute_script(
            """
            const pos = JSON.parse(localStorage.getItem('bookkeeping_pos') || '[]');
            const found = pos.find(p => p.poNum === arguments[0]);
            if (found && typeof window.convertPOToBill === 'function') {
                window.convertPOToBill(found.id);
            }
            """,
            po_num,
        )
        return self.accept_alert_if_present(timeout=3.0)

    def get_po_history_text(self) -> str:
        """Return the text of `#poHistoryBody`."""
        self.driver.execute_script(
            "if (typeof window.renderPOHistory === 'function') window.renderPOHistory();"
        )
        return self.get_text_by_id("poHistoryBody")

    # --- Banking & Bank Rules (`#view-bank`) ---

    def add_bank_rule(
        self,
        rule_name: str,
        keyword_condition: str,
        target_account: str,
        vat_rate: str = "5",
    ) -> None:
        """Open the Bank Rule modal, populate the rule form, and save."""
        self.driver.execute_script("window.openAddBankRuleModal();")
        self.wait_until(lambda d: d.find_element(By.ID, "bankRuleModal").is_displayed())
        self.fill_input("ruleName", rule_name)
        self.fill_input("ruleCondition", keyword_condition)
        self.select_by_value_or_text("ruleAccount", target_account)
        self.fill_input("ruleVat", vat_rate)
        self.driver.execute_script(
            "document.getElementById('bankRuleForm').requestSubmit();"
        )
        self.accept_alert_if_present(timeout=1.5)
        self.wait_until(lambda d: not d.find_element(By.ID, "bankRuleModal").is_displayed())

    def get_bank_rules_text(self) -> str:
        """Return the text of `#bankRulesBody`."""
        return self.get_text_by_id("bankRulesBody")

    def connect_mock_bank_feeds(self) -> None:
        """Trigger `window.connectMockBank()` and wait for simulated Plaid feed rows to render."""
        self.driver.execute_script("window.connectMockBank();")
        self.wait_until(
            lambda d: "Stripe Payout" in d.find_element(By.ID, "bankFeedsBody").text
        )

    def get_bank_feeds_text(self) -> str:
        """Return the text of `#bankFeedsBody`."""
        return self.get_text_by_id("bankFeedsBody")

    # --- Recurring Transactions (`#view-recurring`) ---

    def add_recurring_template(
        self,
        template_name: str,
        frequency: str,
        tx_type: str,
        entity_name: str,
        amount: str,
        next_run_date: str,
    ) -> None:
        """Populate and submit `#addRecurringForm`."""
        self.fill_input("recName", template_name)
        self.select_by_value_or_text("recFrequency", frequency)
        self.select_by_value_or_text("recType", tx_type)
        self.fill_input("recEntity", entity_name)
        self.fill_input("recAmount", amount)
        self.fill_input("recNextRunDate", next_run_date)
        self.driver.execute_script(
            "document.getElementById('addRecurringForm').requestSubmit();"
        )
        self.accept_alert_if_present(timeout=1.5)

    def get_recurring_templates_text(self) -> str:
        """Return the text of `#recurringBody`."""
        return self.get_text_by_id("recurringBody")
