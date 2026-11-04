"""Unit tests for the UAE FTA Audit File (FAF .csv) generator and Tax module integration."""

from __future__ import annotations

from pathlib import Path
import unittest

REPO_ROOT = Path(__file__).resolve().parent.parent
APP_DIR = REPO_ROOT.parent / "bookkeeping-tool"


def _read_index_html_bundle() -> str:
    parts = [(APP_DIR / "index.html").read_text(encoding="utf-8")]
    for path in sorted(APP_DIR.glob("views-*.js")):
        parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)


def _read_script_js_bundle() -> str:
    parts = [(APP_DIR / "script.js").read_text(encoding="utf-8")]
    for path in sorted(APP_DIR.glob("app-*.js")):
        parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)


class FTAAuditFileExportUnitTests(unittest.TestCase):
    """Verify the Export FTA Audit File (FAF) button and FTA-mandated .csv schema."""

    def test_index_html_wires_faf_export_script_and_tax_module_buttons(self) -> None:
        index_html = _read_index_html_bundle()
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

        for sym in ("FTAAuditFile", "exportFTAAuditFile", "buildCsv", "buildFafData", "validate"):
            self.assertIn(sym, faf_js)
        for sec in ("CompInfo", "CompEnd", "MasterData", "MasterDataEnd", "PurcData", "PurcDataEnd", "SuppData", "SuppDataEnd", "GLData", "GLDataEnd"):
            self.assertIn(sec, faf_js)
        for col in (
            "TaxablePersonNameEn", "TaxablePersonNameAr", "TRN", "TaxAgencyName", "TAN",
            "TaxAgentName", "TAAN", "PeriodStart", "PeriodEnd", "FAFCreationDate",
            "ProductVersion", "FAFVersion", "PartyType", "PartyID", "PartyName", "Country",
            "Emirate", "Address", "Email", "Phone", "PaymentTerms", "SupplierName", "SupplierID",
            "SupplierTRN", "SupplierCountry", "SupplierEmirate", "InvoiceNo", "InvoiceDate",
            "PostingDate", "LineNo", "ProductDescription", "GLAccountID", "GLAccountName",
            "Quantity", "UnitPriceAED", "LineValueAED", "VATRate", "VATAmountAED", "TotalAmountAED",
            "FCYCode", "FCYExchangeRate", "LineValueFCY", "VATAmountFCY", "TaxCode",
            "CustomerName", "CustomerID", "CustomerTRN", "CustomerCountry", "CustomerEmirate",
            "SupplyDate", "DiscountAED", "TransactionDate", "AccountID", "AccountName",
            "TransactionID", "JournalType", "SourceDocumentNo", "CounterpartyName",
            "Description", "DebitAmountAED", "CreditAmountAED", "BalanceAED", "Currency",
        ):
            self.assertIn(col, faf_js)


class Vat201ComplianceUnitTests(unittest.TestCase):
    """Verify UAE VAT 201 Boxes 1a-1g Emirate breakdown, Box 3/10 Reverse Charge, Zero-Rated vs Exempt, and transaction persistence."""

    def test_index_html_contains_emirate_boxes_1a_to_1g_and_transaction_tax_fields(self) -> None:
        index_html = _read_index_html_bundle()
        vat201_js_path = APP_DIR / "vat201.js"

        self.assertTrue(vat201_js_path.is_file(), "vat201.js must exist in bookkeeping-tool")
        self.assertIn("vat201.js", index_html)

        for box_id in ("vatBox1a", "vatBox1b", "vatBox1c", "vatBox1d", "vatBox1e", "vatBox1f", "vatBox1g"):
            self.assertIn(f'id="{box_id}"', index_html)
        for emirate in ("Abu Dhabi", "Dubai", "Sharjah", "Ajman", "Umm Al Quwain", "Ras Al Khaimah", "Fujairah"):
            self.assertIn(emirate, index_html)
        for field_id in (
            "custEmirate", "resEmirate", "resVatTreatment", "journalEmirate",
            "expEmirate", "expVatTreatment", "editEntryEmirate", "editEntryVatTreatment",
        ):
            self.assertIn(f'id="{field_id}"', index_html)
        self.assertIn('value="reverse_charge"', index_html)

    def test_script_and_expenses_persist_vat_treatment_and_emirate_on_every_transaction(self) -> None:
        script_js = _read_script_js_bundle()
        expenses_js = (APP_DIR / "expenses.js").read_text(encoding="utf-8")
        vat201_js = (APP_DIR / "vat201.js").read_text(encoding="utf-8")

        for sym in ("VAT201", "calculate", "render", "normalizeTransaction"):
            self.assertIn(sym, vat201_js)
        for sym in ("custEmirate", "resVatTreatment", "resEmirate", "journalEmirate", "VAT201"):
            self.assertIn(sym, script_js)
        for sym in ("expVatTreatment", "expEmirate", "vatTreatment", "emirate"):
            self.assertIn(sym, expenses_js)


class Art59TaxInvoiceAndCreditNoteUnitTests(unittest.TestCase):
    """Verify UAE VAT Executive Regulation Art. 59 & Art. 60 Tax Invoices & Credit Notes (CRN-####)."""

    def test_index_html_contains_supply_date_line_discounts_per_line_vat_and_credit_note_workflow(self) -> None:
        index_html = _read_index_html_bundle()
        credit_notes_js = APP_DIR / "credit-notes.js"

        self.assertTrue(credit_notes_js.is_file(), "credit-notes.js must exist in bookkeeping-tool")
        self.assertIn("credit-notes.js", index_html)

        for token in (
            'id="custSupplyDate"', 'id="custDiscountDisplay"',
            'class="item-discount"', 'class="item-vat-rate', 'class="item-vat-amount',
        ):
            self.assertIn(token, index_html)

        for crn_id in (
            "taxCreditNoteCard", "creditNoteForm", "crnNumber", "crnDate", "crnSupplyDate",
            "crnOriginalInvoice", "crnReason", "crnEntity", "crnLineItemsList",
            "crnDiscountDisplay", "crnSubtotalDisplay", "crnVatDisplay", "crnTotalDisplay",
            "previewCrnBtn", "submitCrnBtn", "creditNotesHistoryBody",
        ):
            self.assertIn(f'id="{crn_id}"', index_html)

    def test_credit_notes_and_einvoice_implement_art59_and_crn_workflow(self) -> None:
        credit_notes_path = APP_DIR / "credit-notes.js"
        self.assertTrue(credit_notes_path.is_file(), "credit-notes.js must exist in bookkeeping-tool")
        credit_notes_js = credit_notes_path.read_text(encoding="utf-8")
        einvoice_js = (APP_DIR / "einvoice-ae.js").read_text(encoding="utf-8")
        vat201_js = (APP_DIR / "vat201.js").read_text(encoding="utf-8")
        faf_js = (APP_DIR / "faf-export.js").read_text(encoding="utf-8")

        for symbol in (
            "TaxCreditNotes", "nextCreditNoteNumber", "CRN-", "Date of Supply",
            "TAX CREDIT NOTE", "TAX INVOICE", "VAT Rate", "VAT Amount",
            "Discount", "Original Invoice", "renderTaxDocumentPreview", "issueCreditNoteFromInvoice",
        ):
            self.assertIn(symbol, credit_notes_js)

        for xml_token in ("381", "CreditNote", "BillingReference", "InvoiceDocumentReference", "ActualDeliveryDate", "AllowanceCharge"):
            self.assertIn(xml_token, einvoice_js)

        self.assertIn("credit_note", vat201_js)
        self.assertIn("CREDIT_NOTE", faf_js)


class PrepaidCreditsAndDrawdownUnitTests(unittest.TestCase):
    """Verify SME-universal Prepaid Balances, Deferred Revenue (2150), COGS routing, and Usage/Drawdown tracking."""

    def test_coa_and_faf_include_2150_deferred_revenue_customer_advances(self) -> None:
        script_js = _read_script_js_bundle()
        faf_js = (APP_DIR / "faf-export.js").read_text(encoding="utf-8")

        self.assertIn("2150", script_js)
        self.assertIn("Deferred Revenue / Customer Advances", script_js)
        self.assertIn("2150", faf_js)
        self.assertIn("Deferred Revenue / Customer Advances", faf_js)

    def test_index_html_contains_universal_accrual_accounts_mode_and_usage_modal(self) -> None:
        index_html = _read_index_html_bundle()

        for token in (
            'value="5000 Cost of Goods Sold"',
            'value="2150 Deferred Revenue / Customer Advances"',
            'value="4100 Service Revenue"',
            'value="4000 Sales Revenue"',
            'id="accrualMode"',
            'id="editAccrualMode"',
            'id="recordAccrualUsageModal"',
            'id="recordUsageAccrualId"',
            'id="recordUsageDate"',
            'id="recordUsageAmount"',
            'id="recordUsageNote"',
            'id="btnSaveAccrualUsage"',
        ):
            self.assertIn(token, index_html)

    def test_script_js_implements_cogs_prepaid_routing_and_usage_drawdown_entries(self) -> None:
        script_js = _read_script_js_bundle()

        for symbol in ("resolvePrepaidExpenseAccount", "recordAccrualUsage", "usageEntries", "scheduleMode", "USE-"):
            self.assertIn(symbol, script_js)

        arch_doc = (REPO_ROOT / "docs" / "technical" / "architecture-and-execution-flow.md").read_text(encoding="utf-8")
        sdd_doc = (REPO_ROOT / "docs" / "technical" / "sdd-system-design.md").read_text(encoding="utf-8")
        drawio_doc = (REPO_ROOT / "docs" / "diagrams" / "data-flow-and-ledger.drawio").read_text(encoding="utf-8")
        self.assertIn("resolvePrepaidExpenseAccount", arch_doc)
        self.assertIn("5000 Cost of Goods Sold", arch_doc)
        self.assertIn("scheduleMode", arch_doc)
        self.assertIn("usageEntries", arch_doc)
        self.assertIn("5000 COGS", drawio_doc)
        for stale in ("posting-repair.js", "recognitionMethod", "drawdownHistory", "bookkeeping_expenses_v1", "#processExpenseBtn"):
            self.assertNotIn(stale, arch_doc)
            self.assertNotIn(stale, sdd_doc)


class BehavioralTaxAndAccountingJsExecutionTests(unittest.TestCase):
    """Execute VAT201, FTAAuditFile, TaxCreditNotes, EInvoiceAE, and PO/Quote preview modules in Node.js."""

    def test_vat201_faf_credit_notes_einvoice_and_previews_execute_behaviorally_in_node(self) -> None:
        import json
        import subprocess

        node_script = r"""
const assert = require('assert');
const path = require('path');
const appDir = process.env.APP_DIR;

const store = {};
global.localStorage = {
    getItem: (k) => (k in store ? store[k] : null),
    setItem: (k, v) => { store[k] = String(v); },
    removeItem: (k) => { delete store[k]; }
};
global.window = {
    localStorage: global.localStorage,
    formatCurrency: (n) => Number(n || 0).toFixed(2)
};

const VAT201 = require(path.join(appDir, 'vat201.js'));
const FTAAuditFile = require(path.join(appDir, 'faf-export.js'));
const TaxCreditNotes = require(path.join(appDir, 'credit-notes.js'));
const EInvoiceAE = require(path.join(appDir, 'einvoice-ae.js'));
const POPreview = require(path.join(appDir, 'po-preview.js'));
const QuotePreview = require(path.join(appDir, 'quote-preview.js'));
const POReceiving = require(path.join(appDir, 'po-receiving.js'));

const settings = {
    companyName: 'Lumen Books LLC',
    companyAddress: 'DIFC, Dubai, UAE',
    companyEmirate: 'Dubai',
    companyTrn: '100234567890003'
};
const history = [
    {
        id: 'inv-1',
        date: '2026-10-05',
        supplyDate: '2026-10-05',
        type: 'customer',
        status: 'posted',
        invoiceNum: 'INV-1001',
        entityName: 'Dubai Client LLC',
        emirate: 'Dubai',
        vatTreatment: 'standard',
        subtotal: '1000.00',
        discount: '0.00',
        tax: '50.00',
        total: '1050.00',
        items: [{ description: 'Consulting', qty: 1, rate: '1000.00', amount: '1000.00', tax: '50.00', vatRate: 5 }]
    },
    {
        id: 'crn-1',
        date: '2026-10-06',
        supplyDate: '2026-10-06',
        type: 'credit_note',
        isCreditNote: true,
        status: 'posted',
        invoiceNum: 'CRN-1001',
        originalInvoiceNum: 'INV-1001',
        creditNoteReason: 'Returned hours',
        entityName: 'Dubai Client LLC',
        emirate: 'Dubai',
        vatTreatment: 'standard',
        subtotal: '200.00',
        discount: '0.00',
        tax: '10.00',
        total: '210.00',
        items: [{ description: 'Consulting return', qty: 1, rate: '200.00', amount: '200.00', tax: '10.00', vatRate: 5 }]
    },
    {
        id: 'inv-ad',
        date: '2026-10-07',
        type: 'customer',
        status: 'posted',
        invoiceNum: 'INV-1002',
        entityName: 'AD Client PJSC',
        emirate: 'Abu Dhabi',
        vatTreatment: 'zero',
        subtotal: '500.00',
        tax: '0.00',
        total: '500.00',
        items: [{ description: 'Export service', qty: 1, rate: '500.00', amount: '500.00', tax: '0.00', vatRate: 0 }]
    },
    {
        id: 'sup-1',
        date: '2026-10-08',
        type: 'supplier',
        status: 'posted',
        invoiceNum: 'BILL-501',
        entityName: 'Cloud Host LLC',
        emirate: 'Dubai',
        vatTreatment: 'standard',
        account: '6200 Software & SaaS',
        subtotal: '400.00',
        tax: '20.00',
        total: '420.00',
        items: [{ description: 'Hosting', qty: 1, unitPrice: '400.00', amount: '400.00', tax: '20.00', account: '6200 Software & SaaS' }]
    }
];
store['bookkeeping_settings'] = JSON.stringify(settings);
store['bookkeeping_history_v2'] = JSON.stringify(history);
store['bookkeeping_customers'] = JSON.stringify([{ name: 'Dubai Client LLC', trn: '100445566778803', address: 'Business Bay, Dubai, UAE' }]);
store['bookkeeping_suppliers'] = JSON.stringify([{ name: 'Cloud Host LLC', trn: '100998877665503', address: 'Dubai Internet City, UAE' }]);

const vatReport = VAT201.calculate(history, settings);
assert.strictEqual(vatReport.emirates['Dubai'].net, 800);
assert.strictEqual(vatReport.emirates['Dubai'].vat, 40);
assert.strictEqual(vatReport.emirates['Dubai'].adj, 10);
assert.strictEqual(vatReport.zeroRated.net, 500);
assert.strictEqual(vatReport.box9.net, 400);
assert.strictEqual(vatReport.box9.vat, 20);
assert.strictEqual(vatReport.netVat, 20);

const fafData = FTAAuditFile.buildFafData({ fromDate: '2026-10-01', toDate: '2026-10-31' });
assert.strictEqual(fafData.totals.glDebitAED, fafData.totals.glCreditAED);
assert.strictEqual(FTAAuditFile.validate(fafData).length, 0);
const fafCsv = FTAAuditFile.buildCsv(fafData);
assert(fafCsv.includes('CompInfo'));
assert(fafCsv.includes('GLData'));
assert(fafCsv.includes('CRN-1001'));
assert(fafCsv.includes('-200.00'));

assert.strictEqual(TaxCreditNotes.nextCreditNoteNumber(history), 'CRN-1002');
const calcLines = TaxCreditNotes.calculateLineItems([{ description: 'Item', qty: 2, rate: 100, discount: 20, vatRate: 5 }]);
assert.strictEqual(calcLines.subtotal, '180.00');
assert.strictEqual(calcLines.tax, '9.00');
assert.strictEqual(calcLines.total, '189.00');
const previewHtml = TaxCreditNotes.renderTaxDocumentPreview({
    ...history[1],
    entityName: '<img src=x onerror=alert(1)>'
}, settings, {});
assert(!previewHtml.includes('<img src=x onerror=alert(1)>'));
assert(previewHtml.includes('&lt;img src=x onerror=alert(1)&gt;'));

const custProfile = { name: 'Dubai Client LLC', trn: '100445566778803', address: 'Business Bay, Dubai, UAE', country: 'AE' };
assert.strictEqual(EInvoiceAE.validate(history[0], settings, custProfile).length, 0);
const xml380 = EInvoiceAE.buildXml(history[0], settings, custProfile);
assert(xml380.includes('<cbc:InvoiceTypeCode>380</cbc:InvoiceTypeCode>'));
assert(xml380.includes('urn:peppol:pint:billing-1@ae-1'));

assert.strictEqual(EInvoiceAE.validate(history[1], settings, custProfile).length, 0);
const xml381 = EInvoiceAE.buildXml(history[1], settings, custProfile);
assert(xml381.includes('<cbc:CreditNoteTypeCode>381</cbc:CreditNoteTypeCode>'));
assert(xml381.includes('<cbc:ID>INV-1001</cbc:ID>'));

const poHtml = POPreview.render({
    poNum: 'PO-1',
    date: '2026-10-10',
    supplierName: '<script>evil()</script>',
    lines: [{ name: 'Server <b>Rack</b>', qty: 2, cost: 500, total: 1000 }],
    total: 1000,
    status: 'Draft'
});
assert(!poHtml.includes('<script>evil()</script>'));
assert(poHtml.includes('&lt;script&gt;evil()&lt;/script&gt;'));

const quoteHtml = QuotePreview.render({
    quoteNum: 'QT-1',
    date: '2026-10-10',
    clientName: '<svg onload=alert(1)>',
    lines: [{ name: 'Audit', qty: 1, price: 300, total: 300 }],
    total: 300
});
assert(!quoteHtml.includes('<svg onload=alert(1)>'));
assert(quoteHtml.includes('&lt;svg onload=alert(1)&gt;'));

const billFromPo = POReceiving.buildBill({
    id: 'po-1',
    poNum: 'PO-100',
    supplierName: 'Hardware Co',
    lines: [{ name: 'SSD', qty: 2, receivedQty: 2, cost: 100 }]
}, { taxAmount: 10 });
assert.strictEqual(billFromPo.entityName, 'Hardware Co');
assert.strictEqual(billFromPo.subtotal, '200.00');
assert.strictEqual(billFromPo.tax, '10.00');
assert.strictEqual(billFromPo.total, '210.00');

console.log(JSON.stringify({ status: 'ok' }));
"""
        proc = subprocess.run(
            ["node", "-e", node_script],
            env={"PATH": "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin", "APP_DIR": str(APP_DIR)},
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout.strip().splitlines()[-1])
        self.assertEqual(payload["status"], "ok")


if __name__ == "__main__":
    unittest.main()
