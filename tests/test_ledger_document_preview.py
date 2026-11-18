"""Unit and browser tests for General Ledger document preview and safe PDF iframe rendering."""

from __future__ import annotations

import base64
from http.server import ThreadingHTTPServer
import json
import threading
import unittest
from urllib.parse import unquote

from tests.browser_shim import sync_playwright

from features.support_server import BookkeepingRequestHandler
from tests.dom_harness import DomComponentHarness

TINY_PDF_DATA_URL = "data:application/pdf;base64," + base64.b64encode(
    b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"
).decode("ascii")
TINY_PNG_DATA_URL = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


class TestLedgerDocumentPreview(unittest.TestCase):
    """Verify safe PDF data URL iframes survive React rendering while XSS vectors remain blocked."""

    def test_react_runtime_allows_safe_pdf_iframe_and_strips_unsafe_iframes(self) -> None:
        dom = DomComponentHarness()
        dom.mount(
            '<div id="htmlSlotTarget"></div><div id="vnodeTarget"></div>',
            modules=("react-runtime.js", "i18n.js", "ui-feedback.js", "views-modals.js"),
        )
        result = dom.run("""
            const slotTarget = document.getElementById('htmlSlotTarget');
            const vnodeTarget = document.getElementById('vnodeTarget');
            const samplePdf = 'data:application/pdf;base64,JVBERi0=';

            ReactDOM.renderHtml(
                slotTarget,
                '<script>window.__xss=1</script>' +
                '<iframe id="jsIframe" src="javascript:alert(1)"></iframe>' +
                '<iframe id="httpIframe" src="https://evil.example/embed.html"></iframe>' +
                '<iframe id="htmlDataIframe" src="data:text/html,<script>window.__xss=2</script>"></iframe>' +
                '<iframe id="srcdocPdfIframe" src="' + samplePdf + '" srcdoc="<script>window.__xss=3</script>"></iframe>' +
                '<iframe id="safePdfFrame" src="' + samplePdf + '" onload="window.__xss=4" width="100%" height="600px" style="border:none;"></iframe>'
            );

            const vnodeRoot = ReactDOM.createRoot(vnodeTarget);
            vnodeRoot.render(React.htmlToVNode(
                '<iframe id="badVnodeIframe" src="javascript:alert(1)"></iframe>' +
                '<iframe id="goodVnodePdf" src="' + samplePdf + '" width="100%" height="400px"></iframe>'
            ));
            await tick(40);

            const safeSlotFrame = slotTarget.querySelector('#safePdfFrame');
            const safeVnodeFrame = vnodeTarget.querySelector('#goodVnodePdf');
            done({
                xssTriggered: window.__xss !== undefined,
                scriptPresent: !!slotTarget.querySelector('script'),
                jsIframePresent: !!slotTarget.querySelector('#jsIframe'),
                httpIframePresent: !!slotTarget.querySelector('#httpIframe'),
                htmlDataIframePresent: !!slotTarget.querySelector('#htmlDataIframe'),
                srcdocPdfIframePresent: !!slotTarget.querySelector('#srcdocPdfIframe'),
                safeSlotFramePresent: !!safeSlotFrame,
                safeSlotFrameSrc: safeSlotFrame ? safeSlotFrame.getAttribute('src') : null,
                safeSlotFrameHasOnload: safeSlotFrame ? safeSlotFrame.hasAttribute('onload') : null,
                badVnodeIframePresent: !!vnodeTarget.querySelector('#badVnodeIframe'),
                safeVnodeFramePresent: !!safeVnodeFrame,
                safeVnodeFrameSrc: safeVnodeFrame ? safeVnodeFrame.getAttribute('src') : null,
            });
        """)

        self.assertFalse(result["xssTriggered"])
        self.assertFalse(result["scriptPresent"])
        self.assertFalse(result["jsIframePresent"])
        self.assertFalse(result["httpIframePresent"])
        self.assertFalse(result["htmlDataIframePresent"])
        self.assertFalse(result["srcdocPdfIframePresent"])
        self.assertTrue(result["safeSlotFramePresent"])
        self.assertEqual(result["safeSlotFrameSrc"], "data:application/pdf;base64,JVBERi0=")
        self.assertFalse(result["safeSlotFrameHasOnload"])
        self.assertFalse(result["badVnodeIframePresent"])
        self.assertTrue(result["safeVnodeFramePresent"])
        self.assertEqual(result["safeVnodeFrameSrc"], "data:application/pdf;base64,JVBERi0=")

    def test_general_ledger_view_button_and_dropdown_preview_all_document_types(self) -> None:
        attachments = {
            "sup-offload-pdf": TINY_PDF_DATA_URL,
            "bank-offload-pdf": TINY_PDF_DATA_URL,
            "jrn-offload-pdf": TINY_PDF_DATA_URL,
            "exp-offload-png": TINY_PNG_DATA_URL,
        }
        entries = [
            {
                "id": "cust-1",
                "type": "customer",
                "status": "posted",
                "date": "2026-03-01",
                "entityName": "Acme Co",
                "invoiceNum": "INV-1001",
                "description": "Consulting",
                "subtotal": "100",
                "tax": "5",
                "total": "105",
                "items": [{"description": "Service", "qty": 1, "amount": 100}],
            },
            {
                "id": "crn-1",
                "type": "credit_note",
                "status": "posted",
                "date": "2026-03-02",
                "entityName": "Acme Co",
                "invoiceNum": "CRN-1001",
                "linkedInvoice": "INV-1001",
                "description": "Return",
                "subtotal": "50",
                "tax": "2.5",
                "total": "52.5",
                "items": [{"description": "Service", "qty": 1, "amount": 50}],
            },
            {
                "id": "sup-offload-pdf",
                "type": "supplier",
                "status": "posted",
                "date": "2026-03-03",
                "entityName": "Sup PDF Offload",
                "invoiceNum": "BILL-1",
                "description": "Bill PDF",
                "subtotal": "200",
                "tax": "10",
                "total": "210",
                "hasFile": True,
            },
            {
                "id": "sup-inline-png",
                "type": "supplier",
                "status": "posted",
                "date": "2026-03-04",
                "entityName": "Sup PNG Inline",
                "invoiceNum": "BILL-2",
                "description": "Bill PNG",
                "subtotal": "200",
                "tax": "10",
                "total": "210",
                "hasFile": True,
                "fileBase64": TINY_PNG_DATA_URL,
            },
            {
                "id": "bank-offload-pdf",
                "type": "bank",
                "status": "posted",
                "date": "2026-03-05",
                "entityName": "ENBD Bank",
                "description": "Bank Stmt PDF",
                "subtotal": "500",
                "tax": "0",
                "total": "500",
                "hasFile": True,
            },
            {
                "id": "jrn-offload-pdf",
                "type": "journal",
                "status": "posted",
                "date": "2026-03-06",
                "entityName": "Journal PDF",
                "description": "Manual JV",
                "drAcc": "6000 Office Supplies",
                "crAcc": "1100 Bank Account",
                "subtotal": "100",
                "total": "100",
                "hasFile": True,
            },
            {
                "id": "exp-offload-png",
                "type": "journal",
                "expenseId": "EXP-1",
                "status": "posted",
                "date": "2026-03-07",
                "entityName": "DEWA",
                "description": "Expense PNG",
                "drAcc": "6300 Utilities",
                "crAcc": "1100 Bank Account",
                "subtotal": "80",
                "total": "80",
                "hasFile": True,
            },
        ]

        server = ThreadingHTTPServer(("127.0.0.1", 0), BookkeepingRequestHandler)
        port = server.server_address[1]
        threading.Thread(target=server.serve_forever, daemon=True).start()

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, executable_path="/usr/bin/chromium")
                ctx = browser.new_context()

                def handle_api(route):
                    url = route.request.url
                    if "/api/v1/attachments" in url and "key=" in url:
                        raw_key = unquote(url.split("key=")[1].split("&")[0])
                        val = next((v for k, v in attachments.items() if raw_key.endswith(k)), None)
                        route.fulfill(
                            status=200 if val else 404,
                            content_type="application/json",
                            body=json.dumps({"data": val} if val else {"error": "not found"}),
                        )
                    elif "/api/v1/state" in url:
                        route.fulfill(
                            status=200,
                            content_type="application/json",
                            body=json.dumps(
                                {
                                    "ok": True,
                                    "state": {
                                        "lumen_accounts": json.dumps(
                                            [{"id": "owner", "role": "owner", "plan": "advance"}]
                                        ),
                                        "bookkeeping_history_v2": json.dumps(entries),
                                        "bookkeeping_settings": "{}",
                                    },
                                }
                            ),
                        )
                    else:
                        route.fulfill(
                            status=200,
                            content_type="application/json",
                            body=json.dumps({"ok": True}),
                        )

                ctx.route("**/api/v1/**", handle_api)
                page = ctx.new_page()
                page_errors: list[str] = []
                page.on("pageerror", lambda e: page_errors.append(str(e)))
                page.goto(f"http://127.0.0.1:{port}/welcome.html", wait_until="domcontentloaded")
                page.evaluate(
                    """() => {
                        sessionStorage.setItem('lumen_current_account', 'owner');
                        sessionStorage.setItem('lumen_active_profile', 'default');
                        sessionStorage.setItem('lumen_session_token', 'tok_preview_test');
                    }"""
                )
                page.goto(f"http://127.0.0.1:{port}/index.html", wait_until="domcontentloaded")
                page.wait_for_function(
                    '() => typeof window.viewFile === "function" && typeof window.loadHistory === "function"'
                )
                page.evaluate('() => window.switchView("view-ledger")')
                page.wait_for_timeout(200)

                cases = [
                    ("cust-1", "Consulting", "invoice"),
                    ("crn-1", "Return", "invoice"),
                    ("sup-offload-pdf", "Bill PDF", "pdf"),
                    ("sup-inline-png", "Bill PNG", "img"),
                    ("bank-offload-pdf", "ENBD Bank", "pdf"),
                    ("jrn-offload-pdf", "Manual JV", "pdf"),
                    ("exp-offload-png", "Expense PNG", "img"),
                ]

                for entry_id, row_text, expected_kind in cases:
                    page.evaluate(
                        """() => {
                            document.getElementById('invoiceModal').style.display = 'none';
                            document.getElementById('modalBody').innerHTML = '';
                        }"""
                    )
                    row = page.locator("#historyBody tr", has_text=row_text)
                    row.locator("button", has_text="View").first.click()
                    page.wait_for_timeout(150)

                    snap = page.evaluate(
                        """() => {
                            const modal = document.getElementById('invoiceModal');
                            const body = document.getElementById('modalBody');
                            const iframe = body.querySelector('iframe');
                            const img = body.querySelector('img');
                            return {
                                modalDisplay: modal.style.display,
                                iframeSrc: iframe ? iframe.getAttribute('src') : null,
                                imgSrc: img ? img.getAttribute('src') : null,
                                hasInvoicePreview: !!body.querySelector('.e-invoice-preview'),
                            };
                        }"""
                    )
                    self.assertEqual(snap["modalDisplay"], "flex", f"{entry_id}: modal did not open")
                    if expected_kind == "pdf":
                        self.assertIsNotNone(snap["iframeSrc"], f"{entry_id}: missing PDF iframe")
                        self.assertTrue(
                            snap["iframeSrc"].startswith("data:application/pdf"),
                            f"{entry_id}: unexpected iframe src {snap['iframeSrc']}",
                        )
                    elif expected_kind == "img":
                        self.assertIsNotNone(snap["imgSrc"], f"{entry_id}: missing image preview")
                        self.assertTrue(snap["imgSrc"].startswith("data:image/"))
                    else:
                        self.assertTrue(snap["hasInvoicePreview"], f"{entry_id}: missing invoice/credit note preview")

                # Verify selecting "View Document" from the row action dropdown also opens PDF previews.
                page.evaluate(
                    """() => {
                        document.getElementById('invoiceModal').style.display = 'none';
                        document.getElementById('modalBody').innerHTML = '';
                    }"""
                )
                page.locator("#historyBody tr", has_text="Bill PDF").locator("select.action-dropdown").select_option(
                    "view"
                )
                page.wait_for_timeout(150)
                dropdown_snap = page.evaluate(
                    """() => {
                        const iframe = document.getElementById('modalBody').querySelector('iframe');
                        return {
                            modalDisplay: document.getElementById('invoiceModal').style.display,
                            iframeSrc: iframe ? iframe.getAttribute('src') : null,
                        };
                    }"""
                )
                self.assertEqual(dropdown_snap["modalDisplay"], "flex")
                self.assertIsNotNone(dropdown_snap["iframeSrc"])
                self.assertTrue(dropdown_snap["iframeSrc"].startswith("data:application/pdf"))
                self.assertEqual(page_errors, [])
                browser.close()
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
