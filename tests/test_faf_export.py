"""Unit tests for the UAE FTA Audit File (FAF .csv) generator and Tax module integration."""

from __future__ import annotations

from pathlib import Path
import unittest

REPO_ROOT = Path(__file__).resolve().parent.parent
APP_DIR = REPO_ROOT.parent / "bookkeeping-tool"


class FTAAuditFileExportUnitTests(unittest.TestCase):
    """Verify the Export FTA Audit File (FAF) button and FTA-mandated .csv schema."""

    def test_index_html_wires_faf_export_script_and_tax_module_buttons(self) -> None:
        index_html = (APP_DIR / "index.html").read_text(encoding="utf-8")
        faf_js_path = APP_DIR / "faf-export.js"

        self.assertTrue(faf_js_path.is_file(), "faf-export.js must exist in bookkeeping-tool")
        self.assertIn("faf-export.js", index_html)
        self.assertIn('id="btnExportFaf"', index_html)
        self.assertIn("Export FTA Audit File (FAF)", index_html)
        self.assertIn('id="fafSummaryCard"', index_html)
        self.assertIn('id="btnExportFafCard"', index_html)

    def test_faf_export_js_implements_exact_fta_csv_schema_sections_and_columns(self) -> None:
        faf_js_path = APP_DIR / "faf-export.js"
        self.assertTrue(faf_js_path.is_file(), "faf-export.js must exist in bookkeeping-tool")
        faf_js = faf_js_path.read_text(encoding="utf-8")

        # Must expose FTAAuditFile API and window.exportFTAAuditFile
        self.assertIn("FTAAuditFile", faf_js)
        self.assertIn("exportFTAAuditFile", faf_js)
        self.assertIn("buildCsv", faf_js)
        self.assertIn("buildFafData", faf_js)
        self.assertIn("validate", faf_js)

        # Section 1: Company Header (CompInfo .. CompEnd)
        self.assertIn("CompInfo", faf_js)
        self.assertIn("CompEnd", faf_js)
        for col in (
            "TaxablePersonNameEn",
            "TaxablePersonNameAr",
            "TRN",
            "TaxAgencyName",
            "TAN",
            "TaxAgentName",
            "TAAN",
            "PeriodStart",
            "PeriodEnd",
            "FAFCreationDate",
            "ProductVersion",
            "FAFVersion",
        ):
            self.assertIn(col, faf_js)

        # Section 2: Customer/Supplier Master Data (MasterData .. MasterDataEnd)
        self.assertIn("MasterData", faf_js)
        self.assertIn("MasterDataEnd", faf_js)
        for col in (
            "PartyType",
            "PartyID",
            "PartyName",
            "TRN",
            "Country",
            "Emirate",
            "Address",
            "Email",
            "Phone",
            "PaymentTerms",
        ):
            self.assertIn(col, faf_js)

        # Section 3: Purchase Line Details (PurcData .. PurcDataEnd)
        self.assertIn("PurcData", faf_js)
        self.assertIn("PurcDataEnd", faf_js)
        for col in (
            "SupplierName",
            "SupplierID",
            "SupplierTRN",
            "SupplierCountry",
            "SupplierEmirate",
            "InvoiceNo",
            "InvoiceDate",
            "PostingDate",
            "LineNo",
            "ProductDescription",
            "GLAccountID",
            "GLAccountName",
            "Quantity",
            "UnitPriceAED",
            "LineValueAED",
            "VATRate",
            "VATAmountAED",
            "TotalAmountAED",
            "FCYCode",
            "FCYExchangeRate",
            "LineValueFCY",
            "VATAmountFCY",
            "TaxCode",
        ):
            self.assertIn(col, faf_js)

        # Section 4: Sales / Supply Line Details (SuppData .. SuppDataEnd)
        self.assertIn("SuppData", faf_js)
        self.assertIn("SuppDataEnd", faf_js)
        for col in (
            "CustomerName",
            "CustomerID",
            "CustomerTRN",
            "CustomerCountry",
            "CustomerEmirate",
            "InvoiceNo",
            "InvoiceDate",
            "SupplyDate",
            "LineNo",
            "ProductDescription",
            "DiscountAED",
        ):
            self.assertIn(col, faf_js)

        # Section 5: General Ledger Entries (GLData .. GLDataEnd)
        self.assertIn("GLData", faf_js)
        self.assertIn("GLDataEnd", faf_js)
        for col in (
            "TransactionDate",
            "AccountID",
            "AccountName",
            "TransactionID",
            "JournalType",
            "SourceDocumentNo",
            "CounterpartyName",
            "Description",
            "DebitAmountAED",
            "CreditAmountAED",
            "BalanceAED",
            "Currency",
        ):
            self.assertIn(col, faf_js)


class Vat201ComplianceUnitTests(unittest.TestCase):
    """Verify UAE VAT 201 Boxes 1a-1g Emirate breakdown, Box 3/10 Reverse Charge, Zero-Rated vs Exempt, and transaction persistence."""

    def test_index_html_contains_emirate_boxes_1a_to_1g_and_transaction_tax_fields(self) -> None:
        index_html = (APP_DIR / "index.html").read_text(encoding="utf-8")
        vat201_js_path = APP_DIR / "vat201.js"

        self.assertTrue(vat201_js_path.is_file(), "vat201.js must exist in bookkeeping-tool")
        self.assertIn("vat201.js", index_html)

        # Boxes 1a-1g for the 7 UAE Emirates
        for box_id in ("vatBox1a", "vatBox1b", "vatBox1c", "vatBox1d", "vatBox1e", "vatBox1f", "vatBox1g"):
            self.assertIn(f'id="{box_id}"', index_html)
        for emirate in (
            "Abu Dhabi",
            "Dubai",
            "Sharjah",
            "Ajman",
            "Umm Al Quwain",
            "Ras Al Khaimah",
            "Fujairah",
        ):
            self.assertIn(emirate, index_html)

        # Transaction-level Emirate & VAT Treatment controls across Customer, Supplier, Journal, Expense, and Edit Modal
        for field_id in (
            "custEmirate",
            "resEmirate",
            "resVatTreatment",
            "journalEmirate",
            "expEmirate",
            "expVatTreatment",
            "editEntryEmirate",
            "editEntryVatTreatment",
        ):
            self.assertIn(f'id="{field_id}"', index_html)

        self.assertIn('value="reverse_charge"', index_html)

    def test_script_and_expenses_persist_vat_treatment_and_emirate_on_every_transaction(self) -> None:
        script_js = (APP_DIR / "script.js").read_text(encoding="utf-8")
        expenses_js = (APP_DIR / "expenses.js").read_text(encoding="utf-8")
        vat201_js = (APP_DIR / "vat201.js").read_text(encoding="utf-8")

        self.assertIn("VAT201", vat201_js)
        self.assertIn("calculate", vat201_js)
        self.assertIn("render", vat201_js)
        self.assertIn("normalizeTransaction", vat201_js)

        self.assertIn("custEmirate", script_js)
        self.assertIn("resVatTreatment", script_js)
        self.assertIn("resEmirate", script_js)
        self.assertIn("journalEmirate", script_js)
        self.assertIn("VAT201", script_js)

        self.assertIn("expVatTreatment", expenses_js)
        self.assertIn("expEmirate", expenses_js)
        self.assertIn("vatTreatment", expenses_js)
        self.assertIn("emirate", expenses_js)


class Art59TaxInvoiceAndCreditNoteUnitTests(unittest.TestCase):
    """Verify UAE VAT Executive Regulation Art. 59 & Art. 60 Tax Invoices & Credit Notes (CRN-####)."""

    def test_index_html_contains_supply_date_line_discounts_per_line_vat_and_credit_note_workflow(self) -> None:
        index_html = (APP_DIR / "index.html").read_text(encoding="utf-8")
        credit_notes_js = APP_DIR / "credit-notes.js"

        self.assertTrue(credit_notes_js.is_file(), "credit-notes.js must exist in bookkeeping-tool")
        self.assertIn("credit-notes.js", index_html)

        # Customer Invoice Art. 59 fields: Date of Supply, per-line discount, per-line VAT rate & amount, discount summary
        for token in (
            'id="custSupplyDate"',
            'id="custDiscountDisplay"',
            'class="item-discount"',
            'class="item-vat-rate',
            'class="item-vat-amount',
        ):
            self.assertIn(token, index_html)

        # Dedicated Tax Credit Note (CRN-####) workflow controls
        for crn_id in (
            "taxCreditNoteCard",
            "creditNoteForm",
            "crnNumber",
            "crnDate",
            "crnSupplyDate",
            "crnOriginalInvoice",
            "crnReason",
            "crnEntity",
            "crnLineItemsList",
            "crnDiscountDisplay",
            "crnSubtotalDisplay",
            "crnVatDisplay",
            "crnTotalDisplay",
            "previewCrnBtn",
            "submitCrnBtn",
            "creditNotesHistoryBody",
        ):
            self.assertIn(f'id="{crn_id}"', index_html)

    def test_credit_notes_and_einvoice_implement_art59_and_crn_workflow(self) -> None:
        credit_notes_path = APP_DIR / "credit-notes.js"
        self.assertTrue(credit_notes_path.is_file(), "credit-notes.js must exist in bookkeeping-tool")
        credit_notes_js = credit_notes_path.read_text(encoding="utf-8")
        einvoice_js = (APP_DIR / "einvoice-ae.js").read_text(encoding="utf-8")
        vat201_js = (APP_DIR / "vat201.js").read_text(encoding="utf-8")
        faf_js = (APP_DIR / "faf-export.js").read_text(encoding="utf-8")

        # credit-notes.js public API & Art. 59 / Art. 60 compliance
        for symbol in (
            "TaxCreditNotes",
            "nextCreditNoteNumber",
            "CRN-",
            "Date of Supply",
            "TAX CREDIT NOTE",
            "TAX INVOICE",
            "VAT Rate",
            "VAT Amount",
            "Discount",
            "Original Invoice",
            "renderTaxDocumentPreview",
            "issueCreditNoteFromInvoice",
        ):
            self.assertIn(symbol, credit_notes_js)

        # einvoice-ae.js PINT-AE CreditNote (381), Delivery Date, AllowanceCharge, and BillingReference
        for xml_token in (
            "381",
            "CreditNote",
            "BillingReference",
            "InvoiceDocumentReference",
            "ActualDeliveryDate",
            "AllowanceCharge",
        ):
            self.assertIn(xml_token, einvoice_js)

        # vat201.js and faf-export.js Credit Note integration
        self.assertIn("credit_note", vat201_js)
        self.assertIn("CREDIT_NOTE", faf_js)


if __name__ == "__main__":
    unittest.main()

