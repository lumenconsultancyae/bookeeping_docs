"""Unit & behavioral tests for WhatsApp-First Workflows:
1. 1-Tap Bilingual (AR/EN) Tax Invoice & Payment Link Share via WhatsApp (`whatsapp-workflows.js`)
2. Bilingual (Arabic/English) FTA Tax Invoice & Credit Note Preview (`credit-notes.js`)
3. Camera Receipt OCR with 15-Digit UAE Vendor TRN & VAT Extraction (`expenses.js` & `views-transactions.js`)
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import unittest

REPO_ROOT = Path(__file__).resolve().parent.parent
BOOKKEEPING_TOOL_DIR = REPO_ROOT.parent / "bookkeeping-tool"


class WhatsAppFirstWorkflowsUnitTests(unittest.TestCase):
    """Verify WhatsApp bilingual sharing, bilingual Tax Invoice preview, and camera receipt Vendor TRN OCR."""

    def test_index_html_and_views_wire_whatsapp_share_bilingual_preview_and_receipt_trn_ocr(self) -> None:
        index_html = (BOOKKEEPING_TOOL_DIR / "index.html").read_text(encoding="utf-8")
        self.assertIn('src="whatsapp-workflows.js', index_html)

        settings_view = (BOOKKEEPING_TOOL_DIR / "views-reports-and-settings.js").read_text(encoding="utf-8")
        self.assertIn('id="companyPaymentLink"', settings_view)

        settings_js = (BOOKKEEPING_TOOL_DIR / "app-settings-and-kpis.js").read_text(encoding="utf-8")
        self.assertIn("companyPaymentLink", settings_js)

        quotes_invoices_view = (BOOKKEEPING_TOOL_DIR / "views-workforce-and-quotes.js").read_text(encoding="utf-8")
        self.assertIn('id="custPaymentLink"', quotes_invoices_view)
        self.assertIn('id="custInvoiceLang"', quotes_invoices_view)
        self.assertIn('id="shareInvoiceWhatsAppBtn"', quotes_invoices_view)

        credit_notes_js = (BOOKKEEPING_TOOL_DIR / "credit-notes.js").read_text(encoding="utf-8")
        self.assertIn("فاتورة ضريبية", credit_notes_js)
        self.assertIn("إشعار دائن ضريبي", credit_notes_js)
        self.assertIn("modalDocLangSelect", credit_notes_js)
        self.assertIn("btnPrintTaxDoc", credit_notes_js)
        self.assertIn("printTaxDocument", credit_notes_js)
        self.assertIn("btnShareWhatsApp", credit_notes_js)
        self.assertIn("shareDocumentViaWhatsApp", credit_notes_js)

        components_css = (BOOKKEEPING_TOOL_DIR / "components.css").read_text(encoding="utf-8")
        self.assertIn("printing-invoice-modal", components_css)
        self.assertIn("#invoiceModal .modal-header", components_css)
        self.assertIn("#invoiceModal .modal-footer", components_css)
        self.assertIn("print-color-adjust: exact", components_css)

        transactions_view = (BOOKKEEPING_TOOL_DIR / "views-transactions.js").read_text(encoding="utf-8")
        self.assertIn('id="expVendorTrn"', transactions_view)
        self.assertIn('id="expTrnStatusBadge"', transactions_view)
        self.assertIn('id="expCameraInput"', transactions_view)
        self.assertIn('capture="environment"', transactions_view)
        self.assertIn('id="expSnapCameraBtn"', transactions_view)

        expenses_js = (BOOKKEEPING_TOOL_DIR / "expenses.js").read_text(encoding="utf-8")
        self.assertIn("expVendorTrn", expenses_js)
        self.assertIn("vendorTrn", expenses_js)
        self.assertIn("extractReceiptTrnAndVat", expenses_js)

    def test_whatsapp_workflows_executes_behaviorally_in_node(self) -> None:
        script_path = BOOKKEEPING_TOOL_DIR / "whatsapp-workflows.js"
        credit_notes_path = BOOKKEEPING_TOOL_DIR / "credit-notes.js"
        self.assertTrue(script_path.is_file(), "Expected whatsapp-workflows.js to exist")

        node_script = f"""
const wf = require({json.dumps(str(script_path))});
const cn = require({json.dumps(str(credit_notes_path))});

const p1 = wf.normalizeUaePhone('050 123 4567');
const p2 = wf.normalizeUaePhone('+971-52-987-6543');
const p3 = wf.normalizeUaePhone('00971551112233');
const p4 = wf.normalizeUaePhone('501234567');
const p5 = wf.normalizeUaePhone('');

const sampleEntry = {{
    invoiceNum: 'INV-1025',
    date: '2026-11-05',
    supplyDate: '2026-11-05',
    dueDate: '2026-11-20',
    entityName: 'Al Masa Trading LLC',
    trn: '100445566778803',
    phone: '050 123 4567',
    subtotal: '10000.00',
    tax: '500.00',
    total: '10500.00',
    paymentLink: 'https://pay.ziina.com/lumen/INV-1025',
    items: [{{ description: 'Cloud ERP Implementation', qty: 1, rate: '10000.00', amount: '10000.00', tax: '500.00' }}]
}};
const sampleSettings = {{
    companyName: 'Lumen Consultancy LLC',
    companyTrn: '100234567890003',
    companyBankIban: 'AE120331234567890123456'
}};
const sampleCust = {{ phone: '050 123 4567', trn: '100445566778803' }};

const msgEn = wf.buildInvoiceMessage(sampleEntry, sampleSettings, sampleCust, 'en');
const msgAr = wf.buildInvoiceMessage(sampleEntry, sampleSettings, sampleCust, 'ar');

const pdfHtmlEn = cn.renderTaxDocumentPreview(sampleEntry, sampleSettings, sampleCust, 'en');
const pdfHtmlAr = cn.renderTaxDocumentPreview(sampleEntry, sampleSettings, sampleCust, 'ar');
const pdfHtml525 = cn.renderTaxDocumentPreview({{
    ...sampleEntry,
    subtotal: '500.00',
    tax: '25.00',
    total: '525.00',
    items: [{{ description: 'Consulting Service', qty: 1, rate: '500.00', amount: '500.00', tax: '25.00' }}]
}}, sampleSettings, sampleCust, 'en');
const pdfHtmlXss = cn.renderTaxDocumentPreview({{
    ...sampleEntry,
    paymentLink: 'javascript:alert(1)'
}}, sampleSettings, sampleCust, 'en');
const msgXss = wf.buildInvoiceMessage({{
    ...sampleEntry,
    paymentLink: 'javascript:alert(1)'
}}, sampleSettings, sampleCust, 'en');

const shareUrlEn = wf.buildWhatsAppShareUrl(sampleEntry, sampleSettings, sampleCust, 'en');
const shareUrlAr = wf.buildWhatsAppShareUrl(sampleEntry, sampleSettings, sampleCust, 'ar');

const ocr1 = wf.extractReceiptTrnAndVat({{
    entityName: 'ADNOC Distribution',
    vendorTrn: 'TRN: 100-2345-6789-0003',
    address: 'Corniche Road, Abu Dhabi',
    subtotal: 200,
    tax: 10,
    total: 210
}});

const ocr2 = wf.extractReceiptTrnAndVat({{
    rawText: 'ENOC Retail LLC\\nالرقم الضريبي TRN: 100987654321003\\nSheikh Zayed Rd, Dubai\\nTotal Incl VAT: AED 105.00\\nVAT 5%: AED 5.00',
    total: 105,
    tax: 0
}});

console.log(JSON.stringify({{
    p1, p2, p3, p4, p5,
    msgEn,
    msgAr,
    pdfHtmlEn,
    pdfHtmlAr,
    pdfHtml525,
    pdfHtmlXss,
    msgXss,
    shareUrlEn,
    shareUrlAr,
    ocr1,
    ocr2,
    validTrn: wf.isValidUaeTrn('100234567890003'),
    invalidTrn: wf.isValidUaeTrn('12345'),
    hasPrintTaxDocument: typeof cn.printTaxDocument === 'function'
}}));
"""
        from tests.js_runner import run_node_script

        proc = run_node_script(node_script, BOOKKEEPING_TOOL_DIR)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = json.loads(proc.stdout.strip())

        self.assertEqual(out["p1"], "971501234567")
        self.assertEqual(out["p2"], "971529876543")
        self.assertEqual(out["p3"], "971551112233")
        self.assertEqual(out["p4"], "971501234567")
        self.assertEqual(out["p5"], "")

        # English-only WhatsApp message & PDF preview
        self.assertIn("TAX INVOICE", out["msgEn"])
        self.assertNotIn("فاتورة ضريبية", out["msgEn"])
        self.assertIn("https://pay.ziina.com/lumen/INV-1025", out["msgEn"])
        self.assertIn('dir="ltr"', out["pdfHtmlEn"])
        self.assertIn("TAX INVOICE", out["pdfHtmlEn"])
        self.assertIn("ei-title-banner", out["pdfHtmlEn"])
        self.assertIn('<div class="ei-header" dir="ltr"', out["pdfHtmlEn"])
        self.assertIn("flex-wrap: nowrap", out["pdfHtmlEn"])
        self.assertIn("max-width: 58%", out["pdfHtmlEn"])
        self.assertIn("table-layout: fixed", out["pdfHtmlEn"])
        self.assertIn("Ten Thousand Five Hundred Dirhams Only.", out["pdfHtmlEn"])
        self.assertIn("Five Hundred and Twenty Five Dirhams Only.", out["pdfHtml525"])
        self.assertIn("Invoice No.", out["pdfHtmlEn"])
        self.assertIn("Invoice Date", out["pdfHtmlEn"])
        self.assertIn("Terms", out["pdfHtmlEn"])
        self.assertIn("Due Date", out["pdfHtmlEn"])
        self.assertIn("Billed To:", out["pdfHtmlEn"])
        self.assertIn("This is a computer generated document and does not need a signature.", out["pdfHtmlEn"])
        self.assertNotIn("Date of Supply", out["pdfHtmlEn"])
        self.assertNotIn("Place of Supply", out["pdfHtmlEn"])
        self.assertNotIn("فاتورة ضريبية", out["pdfHtmlEn"])
        self.assertNotIn("رقم الفاتورة", out["pdfHtmlEn"])
        self.assertNotIn("javascript:alert(1)", out["pdfHtmlXss"])
        self.assertNotIn("javascript:alert(1)", out["msgXss"])

        # Arabic-only WhatsApp message & PDF preview
        self.assertIn("فاتورة ضريبية", out["msgAr"])
        self.assertNotIn("TAX INVOICE", out["msgAr"])
        self.assertIn("رابط الدفع", out["msgAr"])
        self.assertIn("https://pay.ziina.com/lumen/INV-1025", out["msgAr"])
        self.assertIn('dir="rtl"', out["pdfHtmlAr"])
        self.assertIn('<div class="ei-header" dir="ltr"', out["pdfHtmlAr"])
        self.assertIn("فاتورة ضريبية", out["pdfHtmlAr"])
        self.assertIn("رقم الفاتورة", out["pdfHtmlAr"])
        self.assertIn("تاريخ الفاتورة", out["pdfHtmlAr"])
        self.assertIn("شروط الدفع", out["pdfHtmlAr"])
        self.assertIn("تاريخ الاستحقاق", out["pdfHtmlAr"])
        self.assertIn("هذه الوثيقة صادرة آلياً ولا تحتاج إلى توقيع.", out["pdfHtmlAr"])
        self.assertIn('<span dir="ltr">050 123 4567</span>', out["pdfHtmlAr"])
        self.assertNotIn("TAX INVOICE", out["pdfHtmlAr"])
        self.assertNotIn("Invoice No.", out["pdfHtmlAr"])
        self.assertTrue(out["hasPrintTaxDocument"])

        self.assertTrue(out["shareUrlEn"].startswith("https://wa.me/971501234567?text="))
        self.assertTrue(out["shareUrlAr"].startswith("https://wa.me/971501234567?text="))

        self.assertEqual(out["ocr1"]["vendorTrn"], "100234567890003")
        self.assertTrue(out["ocr1"]["isValidTrn"])
        self.assertEqual(out["ocr1"]["emirate"], "Abu Dhabi")
        self.assertEqual(out["ocr1"]["subtotal"], 200)
        self.assertEqual(out["ocr1"]["tax"], 10)
        self.assertEqual(out["ocr1"]["total"], 210)

        self.assertEqual(out["ocr2"]["vendorTrn"], "100987654321003")
        self.assertTrue(out["ocr2"]["isValidTrn"])
        self.assertEqual(out["ocr2"]["emirate"], "Dubai")
        self.assertEqual(out["ocr2"]["tax"], 5)
        self.assertEqual(out["ocr2"]["subtotal"], 100)
        self.assertEqual(out["ocr2"]["total"], 105)

        self.assertTrue(out["validTrn"])
        self.assertFalse(out["invalidTrn"])


if __name__ == "__main__":
    unittest.main()
