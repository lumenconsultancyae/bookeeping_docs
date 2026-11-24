"""Unit and integration tests enforcing strict valid-invoice-only upload validation.

User stories covered:
1. Uploading a PDF containing only dog photos, unrelated prose, corrupt/disguised bytes,
   or non-invoice content is rejected before previewing, populating, or saving to the ledger.
2. Both `agy_service.py` / `invoice_validation.py` (backend prediction proxy), `einvoice_service.py`
   / `einvoice-ae.js` (Peppol XML), and `invoice-validation.js` (frontend validator + Supplier,
   Customer, Expense, Petty Cash, and Bank Statement controllers) enforce valid-document gates.
"""

from __future__ import annotations

import base64
import json
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import MagicMock, patch

import agy_service
import einvoice_service
from features.support_server import BookkeepingRequestHandler
from tests.js_runner import _get_playwright_page, run_node_script

APP_DIR = Path(__file__).resolve().parents[2] / "bookkeeping-tool"

TINY_VALID_PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
TINY_VALID_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


class _RejectingPredictionHandler(BookkeepingRequestHandler):
    """Test server handler returning HTTP 422 invalid_invoice_document on AI predictions."""

    def do_POST(self) -> None:
        if self.path.startswith("/api/v1/prediction/"):
            msg = "PDF contains only dog photos and is not a valid invoice."
            t = json.dumps({"isValidInvoice": False, "documentType": "non_invoice", "rejectionReason": "PDF contains only dog photos."})
            body = json.dumps({"error": {"code": "invalid_invoice_document", "message": msg}, "text": t}).encode("utf-8")
            self._send_bytes(body, "application/json; charset=utf-8", status=422)
            return
        super().do_POST()


class BackendInvoiceValidationTests(unittest.TestCase):
    """Backend `agy_service.py` & `einvoice_service.py` validation for uploaded documents."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), agy_service.AgyPredictionHandler)
        cls.port = cls.server.server_address[1]
        cls.base_url = f"http://127.0.0.1:{cls.port}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()

    def _post_prediction(self, body: dict) -> tuple[int, dict]:
        tok = agy_service.get_state_repo().issue_session_token("owner")
        headers = {"Content-Type": "application/json", "X-Lumen-Client": "lumen-bookkeeping-web", "Origin": "http://localhost:9091", "X-Lumen-Account": "owner", "X-Lumen-Session": tok}
        req = urllib.request.Request(f"{self.base_url}/api/v1/prediction/test", data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as err:
            return err.code, json.loads(err.read().decode("utf-8"))

    @patch("agy_service.subprocess.run")
    def test_rejects_disguised_or_corrupt_pdf_bytes_before_running_agy(self, mock_run: MagicMock) -> None:
        fake_pdf = f"data:application/pdf;base64,{base64.b64encode(b'Just a dog photo, not a PDF').decode('ascii')}"
        status, payload = self._post_prediction({"question": "You are an expert AI accountant processing a SUPPLIER INVOICE.", "uploads": [{"name": "dogs.pdf", "mime": "application/pdf", "data": fake_pdf}]})
        self.assertEqual(status, 422)
        self.assertEqual(payload["error"]["code"], "invalid_invoice_document")
        mock_run.assert_not_called()

    @patch("agy_service.subprocess.run")
    def test_rejects_when_agy_reports_non_invoice_dog_pdf(self, mock_run: MagicMock) -> None:
        resp_str = '```json\n{"isValidInvoice": false, "documentType": "non_invoice", "rejectionReason": "The uploaded PDF only contains photos of dogs and no invoice data."}\n```'
        mock_run.return_value = subprocess.CompletedProcess(args=["agy"], returncode=0, stdout=json.dumps({"conversation_id": "conv-dogs", "status": "SUCCESS", "response": resp_str}) + "\n", stderr="")
        b64_pdf = f"data:application/pdf;base64,{base64.b64encode(TINY_VALID_PDF).decode('ascii')}"
        status, payload = self._post_prediction({"question": "You are an expert AI accountant processing a SUPPLIER INVOICE.", "uploads": [{"name": "dogs_only.pdf", "mime": "application/pdf", "data": b64_pdf}]})
        self.assertEqual(status, 422)
        self.assertEqual(payload["error"]["code"], "invalid_invoice_document")
        self.assertIn("dogs", payload["error"]["message"].lower())
        self.assertIn("isValidInvoice", mock_run.call_args.args[0][-1])

    @patch("agy_service.subprocess.run")
    def test_rejects_when_agy_returns_empty_or_prose_refusal_for_uploaded_invoice(self, mock_run: MagicMock) -> None:
        b64_pdf = f"data:application/pdf;base64,{base64.b64encode(TINY_VALID_PDF).decode('ascii')}"
        for ai_reply in (
            "I cannot extract invoice data because this PDF only shows golden retrievers.",
            '```json\n{"date": "", "invoiceNum": "", "entityName": "Unknown", "items": [], "total": 0}\n```',
        ):
            mock_run.return_value = subprocess.CompletedProcess(args=["agy"], returncode=0, stdout=json.dumps({"conversation_id": "conv-empty", "status": "SUCCESS", "response": ai_reply}) + "\n", stderr="")
            status, payload = self._post_prediction({"question": "You are an expert AI accountant processing a SUPPLIER INVOICE.", "uploads": [{"name": "dogs_only.pdf", "mime": "application/pdf", "data": b64_pdf}]})
            self.assertEqual(status, 422, f"Expected 422 for reply: {ai_reply!r}")
            self.assertEqual(payload["error"]["code"], "invalid_invoice_document")

    @patch("agy_service.subprocess.run")
    def test_rejects_text_extracted_pdf_without_uploads_when_non_invoice(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(args=["agy"], returncode=0, stdout=json.dumps({"conversation_id": "conv-text-only", "status": "SUCCESS", "response": '```json\n{"entityName": "Essay", "total": 0, "items": []}\n```'}) + "\n", stderr="")
        status, payload = self._post_prediction({"question": "Extract the supplier invoice JSON directly from the text below.\nDOCUMENT TEXT:\nGolden retriever training guide", "uploads": []})
        self.assertEqual(status, 422)
        self.assertEqual(payload["error"]["code"], "invalid_invoice_document")

    @patch("agy_service.subprocess.run")
    def test_validates_bank_statement_extractions(self, mock_run: MagicMock) -> None:
        bad_resp = '```json\n{"bankName": "Unknown", "accountNumber": "N/A", "closingBalance": 0, "transactions": []}\n```'
        mock_run.return_value = subprocess.CompletedProcess(args=["agy"], returncode=0, stdout=json.dumps({"conversation_id": "conv-bank-bad", "status": "SUCCESS", "response": bad_resp}) + "\n", stderr="")
        status_bad, payload_bad = self._post_prediction({"question": "You are an expert AI accountant processing a BANK STATEMENT.\nDOCUMENT TEXT:\nDog park notes", "uploads": []})
        self.assertEqual(status_bad, 422)
        self.assertEqual(payload_bad["error"]["code"], "invalid_invoice_document")
        ok_resp = '```json\n{"bankName": "Emirates NBD", "accountNumber": "1029384756", "closingBalance": 14550, "transactions": [{"date": "2026-10-15", "description": "DEWA", "amount": 450, "type": "withdrawal"}]}\n```'
        mock_run.return_value = subprocess.CompletedProcess(args=["agy"], returncode=0, stdout=json.dumps({"conversation_id": "conv-bank-ok", "status": "SUCCESS", "response": ok_resp}) + "\n", stderr="")
        status_ok, payload_ok = self._post_prediction({"question": "You are an expert AI accountant processing a BANK STATEMENT.\nDOCUMENT TEXT:\nEmirates NBD Statement", "uploads": []})
        self.assertEqual(status_ok, 200)
        self.assertIn("Emirates NBD", payload_ok["text"])

    @patch("agy_service.subprocess.run")
    def test_accepts_valid_invoice_upload(self, mock_run: MagicMock) -> None:
        ok_resp = '```json\n{"isValidInvoice": true, "date": "2026-10-15", "invoiceNum": "SUP-100", "entityName": "Acme LLC", "items": [{"description": "Cloud", "qty": 1, "unitPrice": 100, "amount": 100, "tax": 5}], "subtotal": 100, "tax": 5, "total": 105}\n```'
        mock_run.return_value = subprocess.CompletedProcess(args=["agy"], returncode=0, stdout=json.dumps({"conversation_id": "conv-ok", "status": "SUCCESS", "response": ok_resp}) + "\n", stderr="")
        b64_png = f"data:image/png;base64,{base64.b64encode(TINY_VALID_PNG).decode('ascii')}"
        status, payload = self._post_prediction({"question": "You are an expert AI accountant processing a SUPPLIER INVOICE.", "uploads": [{"name": "invoice.png", "mime": "image/png", "data": b64_png}]})
        self.assertEqual(status, 200)
        self.assertIn("Acme LLC", payload["text"])

    def test_peppol_xml_inbound_parser_rejects_empty_zero_or_placeholder_xml(self) -> None:
        res_empty = einvoice_service.parse_inbound_peppol_xml("<Invoice></Invoice>")
        self.assertFalse(res_empty["ok"])
        res_placeholder = einvoice_service.parse_inbound_peppol_xml(
            """<Invoice xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
                        xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
                <cbc:ID>INV-001</cbc:ID>
                <cac:AccountingSupplierParty><cac:Party><cac:PartyName><cbc:Name>Unknown</cbc:Name></cac:PartyName></cac:Party></cac:AccountingSupplierParty>
                <cac:LegalMonetaryTotal><cbc:TaxInclusiveAmount>105.00</cbc:TaxInclusiveAmount></cac:LegalMonetaryTotal>
            </Invoice>"""
        )
        self.assertFalse(res_placeholder["ok"])
        res_zero = einvoice_service.parse_inbound_peppol_xml(
            """<Invoice xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
                        xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
                <cbc:ID>INV-002</cbc:ID>
                <cac:AccountingSupplierParty><cac:Party><cac:PartyName><cbc:Name>Al Noor LLC</cbc:Name></cac:PartyName></cac:Party></cac:AccountingSupplierParty>
                <cac:LegalMonetaryTotal><cbc:TaxInclusiveAmount>0.00</cbc:TaxInclusiveAmount></cac:LegalMonetaryTotal>
            </Invoice>"""
        )
        self.assertFalse(res_zero["ok"])


class FrontendInvoiceValidatorUnitTests(unittest.TestCase):
    """Unit tests for `bookkeeping-tool/invoice-validation.js` and `einvoice-ae.js` rules."""

    def test_validator_rejects_dogs_non_invoice_and_invalid_bytes_while_allowing_real_invoices(self) -> None:
        validator_path = APP_DIR / "invoice-validation.js"
        einvoice_path = APP_DIR / "einvoice-ae.js"
        self.assertTrue(validator_path.is_file(), "Expected compiled invoice-validation.js to exist")

        node_script = f"""
const assert = require('assert');
const V = require({json.dumps(str(validator_path))});
const E = require({json.dumps(str(einvoice_path))});

// 1. Magic byte & file metadata validation (PDF, PNG, JPG, CSV, XML)
assert.strictEqual(V.validateUploadBytes(new Uint8Array([0x25, 0x50, 0x44, 0x46, 0x2d]), 'application/pdf', 'inv.pdf').valid, true);
assert.strictEqual(V.validateUploadBytes(new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]), 'image/png', 'inv.png').valid, true);
assert.strictEqual(V.validateUploadBytes(new Uint8Array([0xff, 0xd8, 0xff, 0xe0]), 'image/jpeg', 'inv.jpg').valid, true);
assert.strictEqual(V.validateUploadBytes(new TextEncoder().encode('Dog photo text'), 'application/pdf', 'dogs.pdf').valid, false);
assert.strictEqual(V.validateUploadBytes(new Uint8Array([]), 'application/pdf', 'empty.pdf').valid, false);
assert.strictEqual(V.validateUploadFileMeta({{ name: 'dogs.txt', type: 'text/plain', size: 120 }}).valid, false);
assert.strictEqual(V.validateUploadFileMeta({{ name: 'empty.pdf', type: 'application/pdf', size: 0 }}).valid, false);
assert.strictEqual(V.validateUploadFileMeta({{ name: 'inv.xml', type: 'text/xml', size: 200 }}, {{ allowXml: true, allowPdf: false, allowImages: false }}).valid, true);
assert.strictEqual(V.validateUploadBytes(new TextEncoder().encode('<?xml version="1.0"?><Invoice></Invoice>'), 'text/xml', 'inv.xml', {{ allowXml: true, allowPdf: false, allowImages: false }}).valid, true);
assert.strictEqual(V.validateUploadBytes(new TextEncoder().encode('<!DOCTYPE html><html></html>'), 'text/xml', 'bad.xml', {{ allowXml: true, allowPdf: false, allowImages: false }}).valid, false);

// 2. Extracted PDF text evidence check
assert.strictEqual(V.hasInvoiceTextEvidence('Golden retriever dogs playing in the Dubai park with puppies and bones.'), false);
assert.strictEqual(V.hasInvoiceTextEvidence('Leccion 1: Hola me llamo Maria. Buenos dias a todos los estudiantes.'), false);
assert.strictEqual(V.hasInvoiceTextEvidence('TAX INVOICE # MFZ-339673 Supplier: Meydan Free Zone Total: 12520.00 AED'), true);
assert.strictEqual(V.hasInvoiceTextEvidence('فاتورة ضريبية رقم 1001 المجموع 105.00 د.إ'), true);

// 3. Extracted AI payload validation (supplier, customer, expense, petty_cash, bank_statement)
assert.strictEqual(V.validateExtractedInvoice(null, 'supplier').valid, false);
assert.strictEqual(V.validateExtractedInvoice({{}}, 'supplier').valid, false);
assert.strictEqual(V.validateExtractedInvoice({{ isValidInvoice: false, documentType: 'non_invoice', rejectionReason: 'PDF contains only dog pictures', entityName: 'Fake Guess', total: 100 }}, 'supplier').valid, false);
assert.strictEqual(V.validateExtractedInvoice({{ date: 'Invoice Date', invoiceNum: 'Exact invoice number', entityName: 'Supplier Name', subtotal: 0, tax: 0, total: 0, items: [] }}, 'supplier').valid, false);
assert.strictEqual(V.validateExtractedInvoice({{ entityName: 'Unknown', invoiceNum: 'N/A', total: 0, items: [] }}, 'customer').valid, false);
assert.strictEqual(V.validateExtractedInvoice([], 'petty_cash').valid, false);
assert.strictEqual(V.validateExtractedInvoice([{{ isValidInvoice: false, rejectionReason: 'Dogs only' }}], 'petty_cash').valid, false);
assert.strictEqual(V.validateExtractedDocument({{ bankName: 'Unknown', accountNumber: 'N/A', closingBalance: 0, transactions: [] }}, 'bank_statement').valid, false);
assert.strictEqual(V.validateExtractedDocument({{ bankName: 'Emirates NBD', accountNumber: '1029384756', closingBalance: 14550, transactions: [{{ date: '2026-10-15', description: 'DEWA', amount: 450, type: 'withdrawal' }}] }}, 'bank_statement').valid, true);

// 4. Valid payloads must pass
assert.strictEqual(V.validateExtractedInvoice({{ date: '2026-10-15', invoiceNum: 'SUP-8001', entityName: 'Gulf Cloud Infrastructure LLC', items: [{{ description: 'Cloud Compute', qty: 1, unitPrice: 2000, amount: 2000, tax: 100 }}], subtotal: 2000, tax: 100, total: 2100 }}, 'supplier').valid, true);
assert.strictEqual(V.validateExtractedInvoice({{ date: '2026-10-22', entityName: 'ADNOC Distribution', description: 'Fuel', subtotal: 200, tax: 10, total: 210 }}, 'expense').valid, true);
assert.strictEqual(V.validateExtractedInvoice([{{ date: '2026-10-12', reference: 'PC-901', description: 'Printer Toner', tax: 10, total: 210 }}], 'petty_cash').valid, true);

// 5. EInvoiceAE.parseInboundXml rejects placeholder / zero-value XML
assert.strictEqual(E.parseInboundXml('<Invoice></Invoice>').ok, false);
assert.strictEqual(E.parseInboundXml('<Invoice><cbc:ID>INV-1</cbc:ID><cac:AccountingSupplierParty><cac:Party><cac:PartyName><cbc:Name>Unknown</cbc:Name></cac:PartyName></cac:Party></cac:AccountingSupplierParty><cac:LegalMonetaryTotal><cbc:TaxInclusiveAmount>100</cbc:TaxInclusiveAmount></cac:LegalMonetaryTotal></Invoice>').ok, false);

console.log('INVOICE_VALIDATOR_OK');
"""
        proc = run_node_script(node_script, APP_DIR)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("INVOICE_VALIDATOR_OK", proc.stdout)


class ControllerDomRejectionTests(unittest.TestCase):
    """Real-browser tests verifying Supplier, Customer, Expense, Petty Cash, and Bank views block non-invoices."""

    def test_all_document_views_reject_dogs_pdf_without_attaching_populating_or_opening_review(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), _RejectingPredictionHandler)
        port = server.server_address[1]
        threading.Thread(target=server.serve_forever, daemon=True).start()

        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                dogs_pdf_path = Path(tmp_dir) / "dogs_only.pdf"
                dogs_pdf_path.write_bytes(TINY_VALID_PDF)

                page = _get_playwright_page()
                page.goto(f"http://127.0.0.1:{port}/welcome.html", wait_until="domcontentloaded")
                page.evaluate(
                    """() => {
                        sessionStorage.setItem('lumen_current_account', 'owner');
                        sessionStorage.setItem('lumen_active_profile', 'default');
                        sessionStorage.setItem('lumen_session_token', 'tok_validation_test');
                        localStorage.setItem('lumen_accounts', JSON.stringify([{id: 'owner', role: 'owner', plan: 'advance'}]));
                    }"""
                )
                page.goto(f"http://127.0.0.1:{port}/index.html", wait_until="domcontentloaded")
                for _ in range(40):
                    ready = page.evaluate(
                        """() => Boolean(
                            window.LumenInvoiceValidator &&
                            window.LumenUI &&
                            document.getElementById('fileInput') &&
                            document.getElementById('custFileInput') &&
                            document.getElementById('expFileInput') &&
                            document.getElementById('journalFileInput') &&
                            document.getElementById('bankFile')
                        )"""
                    )
                    if ready:
                        break
                    time.sleep(0.1)
                self.assertTrue(ready, "Expected Lumen controllers and file inputs to mount")

                page.evaluate(
                    """() => {
                        window.__capturedToasts = [];
                        const origToast = window.LumenUI.toast.bind(window.LumenUI);
                        window.LumenUI.toast = (msg, type, ...rest) => {
                            window.__capturedToasts.push({ msg, type });
                            return origToast(msg, type, ...rest);
                        };
                        // Simulate a partial heuristic candidate on customer PDF to ensure form fields stay clean on AI rejection
                        window.parseInvoicePdfText = () => ({
                            entityName: 'Dog Park Partial Header',
                            invoiceNum: '',
                            total: 0,
                            items: []
                        });
                    }"""
                )

                # 1. Supplier Bills view
                page.evaluate('() => window.switchView("view-supplier")')
                time.sleep(0.1)
                page.locator("#fileInput").set_input_files(str(dogs_pdf_path))
                time.sleep(0.1)
                page.locator("#processBtn").click()
                time.sleep(0.25)

                # 2. Customer Invoices view (auto-analyzes on file change)
                page.evaluate('() => window.switchView("view-customer")')
                time.sleep(0.1)
                page.locator("#custEntity").evaluate("(el) => { el.value = ''; }")
                page.locator("#custInvoiceNum").evaluate("(el) => { el.value = ''; }")
                page.locator("#custFileInput").set_input_files(str(dogs_pdf_path))
                time.sleep(0.25)

                # 3. Expense Bills view (auto-analyzes on file change)
                page.evaluate('() => window.switchView("view-expense")')
                time.sleep(0.1)
                page.locator("#expFileInput").set_input_files(str(dogs_pdf_path))
                time.sleep(0.25)

                # 4. Petty Cash / Journal view
                page.evaluate('() => window.switchView("view-journal")')
                time.sleep(0.1)
                page.locator("#journalFileInput").set_input_files(str(dogs_pdf_path))
                time.sleep(0.1)
                page.locator("#btnProcessJournalFile").click()
                time.sleep(0.25)

                # 5. Bank Reconciliation view
                page.evaluate('() => window.switchView("view-bank")')
                time.sleep(0.1)
                page.locator("#bankFile").set_input_files(str(dogs_pdf_path))
                time.sleep(0.1)
                page.locator("#processBankBtn").click()
                time.sleep(0.25)

                res = page.evaluate(
                    """() => ({
                        toasts: window.__capturedToasts || [],
                        supplierResultVisible: document.getElementById('resultCard').style.display !== 'none',
                        supplierPreviewHtml: document.getElementById('supplierVisualPreview').innerHTML,
                        supplierUploadVisible: document.getElementById('uploadBox').style.display !== 'none',
                        custAttachment: typeof window.getCustCurrentBase64Image === 'function' ? window.getCustCurrentBase64Image() : 'missing',
                        custPreviewHtml: document.getElementById('custVisualPreview').innerHTML,
                        custBannerText: document.getElementById('custAiBanner').textContent,
                        custUploadVisible: document.getElementById('custUploadBox').style.display !== 'none',
                        custEntityValue: document.getElementById('custEntity').value,
                        expPreviewHtml: document.getElementById('expVisualPreview').innerHTML,
                        expBannerText: document.getElementById('expAiBanner').textContent,
                        expUploadVisible: document.getElementById('expUploadBox').style.display !== 'none',
                        journalReviewVisible: document.getElementById('pettyCashReviewSection').style.display !== 'none',
                        journalPreviewHtml: document.getElementById('pettyCashVisualPreview').innerHTML,
                        journalUploadVisible: document.getElementById('journalUploadBox').style.display !== 'none',
                        bankPreviewVisible: document.getElementById('bankFilePreview').style.display !== 'none',
                        bankNameValue: document.getElementById('resBankName').value,
                        bankUploadVisible: document.getElementById('bankUploadBox').style.display !== 'none',
                    })"""
                )

            self.assertFalse(res["supplierResultVisible"])
            self.assertEqual(res["supplierPreviewHtml"], "")
            self.assertTrue(res["supplierUploadVisible"])
            self.assertIsNone(res["custAttachment"])
            self.assertEqual(res["custPreviewHtml"], "")
            self.assertIn("dog", res["custBannerText"].lower())
            self.assertTrue(res["custUploadVisible"])
            self.assertEqual(res["custEntityValue"], "")
            self.assertEqual(res["expPreviewHtml"], "")
            self.assertIn("dog", res["expBannerText"].lower())
            self.assertTrue(res["expUploadVisible"])
            self.assertFalse(res["journalReviewVisible"])
            self.assertEqual(res["journalPreviewHtml"], "")
            self.assertTrue(res["journalUploadVisible"])
            self.assertFalse(res["bankPreviewVisible"])
            self.assertEqual(res["bankNameValue"], "")
            self.assertTrue(res["bankUploadVisible"])
            self.assertTrue(any(t["type"] == "error" for t in res["toasts"]))
        finally:
            server.shutdown()
            server.server_close()

    def test_cloudflare_multipage_saas_invoice_extraction_and_supplier_fallback(self) -> None:
        """Verify 7-page Cloudflare USD SaaS invoice (`IN-86000612`) extracts date, supplier, customer, USD currency, and billed line item without 61 $0.00 usage rows."""
        cloudflare_text = """
        IN-86000612 · $5.00 USD due October 28, 2026 Page 1 of 7
        Invoice
        Invoice number IN-86000612
        Date of issue October 28, 2026
        Date due October 28, 2026
        Cloudflare, Inc. @cloudflare
        101 Townsend Street
        San Francisco, California 94107
        United States
        billing@cloudflare.com
        US EIN 27-0805829
        Bill to
        Wilson Guevara
        LAGO VISTA B 1416
        UAE
        United Arab Emirates
        lumenconsultancy.ae@gmail.com
        $5.00 USD due October 28, 2026
        Pay online
        VAT-Code: AES-000D
        Description Qty Unit price Amount
        R2 SQL - Bytes Scanned
        Sep 28–Oct 27, 2026
        0 $0.0025 $0.00
        R2 Data Catalog - Objects Processed (first 1mm included)
        Sep 28–Oct 27, 2026
        0 $2.00 per 1,000,000 $0.00
        R2 Paid
        Oct 28–Nov 27, 2026
        1 $0.00 $0.00
        IN-86000612 · $5.00 USD due October 28, 2026 Page 7 of 7
        Queues - Enabled
        Oct 28–Nov 27, 2026
        1 $0.00 $0.00
        Workers Paid
        Oct 28–Nov 27, 2026
        1 $5.00 $5.00
        Subtotal $5.00
        Total $5.00
        Amount due $5.00 USD
        """

        prediction_mode = {"mode": "timeout"}

        class _ConfigurablePredictionHandler(BookkeepingRequestHandler):
            def do_POST(self) -> None:
                if self.path.startswith("/api/v1/prediction/"):
                    mode = prediction_mode["mode"]
                    if mode == "http_422":
                        msg = "No valid invoice amounts or line items were found in the uploaded document."
                        body = json.dumps({"error": {"code": "invalid_invoice_document", "message": msg}}).encode("utf-8")
                        self._send_bytes(body, "application/json; charset=utf-8", status=422)
                        return
                    if mode == "partial_zero_aed":
                        zero_item = {"description": "R2 SQL - Bytes Scanned", "qty": 0, "unitPrice": 0.0025, "amount": 0, "tax": 0, "account": "6200 Software & SaaS", "category": "OpEx"}
                        ai_json = json.dumps({"isValidInvoice": True, "date": "2026-10-28", "invoiceNum": "IN-86000612", "entityName": "Cloudflare, Inc.", "currency": "AED", "subtotal": 0, "tax": 0, "total": 0, "items": [zero_item]})
                        self._send_bytes(json.dumps({"text": f"```json\n{ai_json}\n```"}).encode("utf-8"), "application/json; charset=utf-8", status=200)
                        return
                    body = json.dumps({"error": {"code": "prediction_timeout", "message": "AI prediction timed out."}}).encode("utf-8")
                    self._send_bytes(body, "application/json; charset=utf-8", status=504)
                    return
                super().do_POST()

        server = ThreadingHTTPServer(("127.0.0.1", 0), _ConfigurablePredictionHandler)
        port = server.server_address[1]
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                cf_pdf_path = Path(tmp_dir) / "Email Subs - Oct 2026.pdf"
                cf_pdf_path.write_bytes(TINY_VALID_PDF)

                page = _get_playwright_page()
                page.goto(f"http://127.0.0.1:{port}/welcome.html", wait_until="domcontentloaded")
                page.evaluate("() => { sessionStorage.setItem('lumen_current_account', 'owner'); sessionStorage.setItem('lumen_active_profile', 'default'); sessionStorage.setItem('lumen_session_token', 'tok_cf_test'); localStorage.setItem('lumen_accounts', JSON.stringify([{id: 'owner', role: 'owner', plan: 'advance'}])); }")
                page.goto(f"http://127.0.0.1:{port}/index.html", wait_until="domcontentloaded")
                for _ in range(40):
                    if page.evaluate("() => typeof window.parseInvoicePdfText === 'function'"):
                        break
                    time.sleep(0.1)

                variants = (
                    cloudflare_text,
                    cloudflare_text.replace("IN-86000612", "IN\x0086000612").replace("–", "\x00"),
                    cloudflare_text.replace("Invoice number IN-86000612", "Invoice number IN 86000612").replace("IN-86000612 ·", "IN - 86000612 ·").replace("–", " "),
                )
                for variant_text in variants:
                    parsed = page.evaluate("(txt) => window.parseInvoicePdfText(txt)", variant_text)
                    self.assertIsNotNone(parsed)
                    self.assertEqual((parsed.get("invoiceNum"), parsed.get("date"), parsed.get("dueDate")), ("IN-86000612", "2026-10-28", "2026-10-28"))
                    self.assertEqual((parsed.get("supplierName"), parsed.get("entityName"), parsed.get("email")), ("Cloudflare, Inc.", "Wilson Guevara", "lumenconsultancy.ae@gmail.com"))
                    self.assertEqual((parsed.get("currency"), parsed.get("subtotal"), parsed.get("tax"), parsed.get("total")), ("USD", 5, 0, 5))
                    items = parsed.get("items") or []
                    self.assertEqual(len(items), 1)
                    self.assertEqual((items[0].get("description"), items[0].get("amount")), ("Workers Paid", 5))

                email_only_bill_to = cloudflare_text.replace("Wilson Guevara\n        LAGO VISTA B 1416\n        UAE\n        United Arab Emirates\n        ", "")
                parsed_email_only = page.evaluate("(txt) => window.parseInvoicePdfText(txt)", email_only_bill_to)
                self.assertIsNotNone(parsed_email_only)
                self.assertEqual((parsed_email_only.get("email"), parsed_email_only.get("entityName")), ("lumenconsultancy.ae@gmail.com", "lumenconsultancy.ae@gmail.com"))

                for mode in ("timeout", "http_422", "partial_zero_aed"):
                    prediction_mode["mode"] = mode
                    page.evaluate(
                        "(txt) => { window.extractPdfTextClientSide = async () => txt; window.switchView('view-supplier'); window.initSupplierForm(); document.getElementById('resultCard').style.display = 'none'; }",
                        cloudflare_text.replace("Invoice number IN-86000612", "Invoice number IN 86000612").replace("–", " "),
                    )
                    time.sleep(0.1)
                    page.locator("#fileInput").set_input_files(str(cf_pdf_path))
                    time.sleep(0.1)
                    page.locator("#processBtn").click()
                    for _ in range(30):
                        if page.evaluate("() => document.getElementById('resultCard').style.display !== 'none'"):
                            break
                        time.sleep(0.1)
                    sup_state = page.evaluate(
                        """() => ({
                            visible: document.getElementById('resultCard').style.display !== 'none',
                            invNum: document.getElementById('resInvoiceNum').value, date: document.getElementById('resDate').value,
                            entity: document.getElementById('resEntity').value, currency: document.getElementById('resCurrency').value,
                            vatTreatment: document.getElementById('resVatTreatment').value, subtotal: document.getElementById('resSubtotal').value,
                            tax: document.getElementById('resTax').value, total: document.getElementById('resTotal').value,
                            lineCount: document.querySelectorAll('#supplierLineItems .line-item-row').length,
                            previewHasIframe: document.getElementById('supplierVisualPreview').innerHTML.includes('<iframe'),
                        })"""
                    )
                    self.assertTrue(sup_state["visible"], f"Failed in mode={mode}")
                    self.assertEqual((sup_state["invNum"], sup_state["date"], sup_state["entity"]), ("IN-86000612", "2026-10-28", "Cloudflare, Inc."))
                    self.assertEqual((sup_state["currency"], sup_state["vatTreatment"], sup_state["lineCount"]), ("USD", "zero", 1))
                    self.assertEqual((sup_state["subtotal"], sup_state["tax"], sup_state["total"]), ("18.38", "0.00", "18.38"))
                    self.assertTrue(sup_state["previewHasIframe"])

                page.evaluate("() => { window.switchView('view-customer'); }")
                time.sleep(0.1)
                page.locator("#custFileInput").set_input_files(str(cf_pdf_path))
                for _ in range(30):
                    if page.evaluate("() => document.getElementById('custInvoiceNum').value === 'IN-86000612'"):
                        break
                    time.sleep(0.1)
                cust_state = page.evaluate("() => ({ invNum: document.getElementById('custInvoiceNum').value, entity: document.getElementById('custEntity').value, email: document.getElementById('custEmail') ? document.getElementById('custEmail').value : '', currency: document.getElementById('custCurrency').value, lineCount: document.querySelectorAll('#custLineItemsList .line-item-row').length })")
                self.assertEqual((cust_state["invNum"], cust_state["entity"], cust_state["email"], cust_state["currency"], cust_state["lineCount"]), ("IN-86000612", "Wilson Guevara", "lumenconsultancy.ae@gmail.com", "USD", 1))
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
