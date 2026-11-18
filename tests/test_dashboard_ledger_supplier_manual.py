"""Browser tests for Dashboard Cash Flow graph updates, Ledger entry viewer, and manual Supplier Bills."""

from __future__ import annotations

from http.server import ThreadingHTTPServer
import json
import threading
import unittest

from tests.browser_shim import sync_playwright

from features.support_server import BookkeepingRequestHandler


def _start_test_server(entries: list[dict] | None = None, suppliers: list[dict] | None = None):
    history = entries or []
    supplier_list = suppliers or []
    server = ThreadingHTTPServer(("127.0.0.1", 0), BookkeepingRequestHandler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()

    def handle_api(route):
        url = route.request.url
        if "/api/v1/state" in url:
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
                            "bookkeeping_history_v2": json.dumps(history),
                            "bookkeeping_suppliers": json.dumps(supplier_list),
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

    return server, port, handle_api


def _open_authenticated_app(browser, port: int, handle_api):
    ctx = browser.new_context()
    ctx.route("**/api/v1/**", handle_api)
    page = ctx.new_page()
    page_errors: list[str] = []
    page.on("pageerror", lambda e: page_errors.append(str(e)))
    page.goto(f"http://127.0.0.1:{port}/welcome.html", wait_until="domcontentloaded")
    page.evaluate(
        """() => {
            sessionStorage.setItem('lumen_current_account', 'owner');
            sessionStorage.setItem('lumen_active_profile', 'default');
            sessionStorage.setItem('lumen_session_token', 'tok_feature_test');
        }"""
    )
    page.goto(f"http://127.0.0.1:{port}/index.html", wait_until="domcontentloaded")
    page.wait_for_function(
        '() => typeof window.updateDashboard === "function" && typeof window.viewFile === "function" && typeof window.Chart !== "undefined"'
    )
    return ctx, page, page_errors


class TestDashboardGraphLedgerViewAndManualSupplier(unittest.TestCase):
    """Verify Dashboard graph expense updates, General Ledger entry detail view, and manual Supplier Bills."""

    def test_dashboard_graph_updates_for_recorded_expenses_across_months_and_periods(self) -> None:
        server, port, handle_api = _start_test_server()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, executable_path="/usr/bin/chromium")
                _ctx, page, page_errors = _open_authenticated_app(browser, port, handle_api)

                # Record a direct expense dated in February 2026 (outside default last-6-months from Nov 2026)
                page.evaluate('() => window.switchView("view-expense")')
                page.wait_for_timeout(150)
                page.fill("#expDate", "2026-02-15")
                page.fill("#expPayee", "DEWA Utility")
                page.fill("#expDesc", "Electricity Bill Feb")
                page.fill("#expAmount", "750")
                page.click("#expSaveBtn")
                page.wait_for_timeout(200)

                # Also record a 2025-11-10 expense to verify years never collide on 'Nov'
                page.fill("#expDate", "2025-11-10")
                page.fill("#expPayee", "Etisalat")
                page.fill("#expDesc", "Internet Nov 2025")
                page.fill("#expAmount", "300")
                page.click("#expSaveBtn")
                page.wait_for_timeout(200)

                page.evaluate('() => window.switchView("view-dashboard")')
                page.wait_for_timeout(250)

                all_time_snap = page.evaluate(
                    """() => {
                        const inst = window.cashFlowChartInstance;
                        const d = inst && (inst.data || (inst.config && inst.config.data));
                        return {
                            labels: d ? d.labels : [],
                            cashOut: d && d.datasets[1] ? d.datasets[1].data : [],
                            kpiExp: document.getElementById('kpiExpenses')?.textContent,
                        };
                    }"""
                )
                self.assertIn(750.0, all_time_snap["cashOut"], f"Feb 2026 expense missing from graph: {all_time_snap}")
                self.assertIn(300.0, all_time_snap["cashOut"], f"Nov 2025 expense missing from graph: {all_time_snap}")

                # Filter Dashboard Period to Year 2026, Whole Year -> must include 750 but NOT 2025's 300
                page.select_option("#dashboardYearFilter", "2026")
                page.wait_for_timeout(200)
                y2026_snap = page.evaluate(
                    """() => {
                        const inst = window.cashFlowChartInstance;
                        const d = inst && (inst.data || (inst.config && inst.config.data));
                        return {
                            labels: d ? d.labels : [],
                            cashOut: d && d.datasets[1] ? d.datasets[1].data : [],
                        };
                    }"""
                )
                self.assertIn(750.0, y2026_snap["cashOut"], f"2026 graph missing Feb 750: {y2026_snap}")
                self.assertNotIn(300.0, y2026_snap["cashOut"], f"2026 graph leaked 2025 300: {y2026_snap}")
                self.assertEqual(sum(y2026_snap["cashOut"]), 750.0, f"Unexpected 2026 sum: {y2026_snap}")

                self.assertEqual(page_errors, [])
                browser.close()
        finally:
            server.shutdown()
            server.server_close()

    def test_ledger_allows_viewing_any_recorded_entry_and_filtering_by_status(self) -> None:
        entries = [
            {
                "id": "exp-manual-1",
                "type": "journal",
                "status": "posted",
                "date": "2026-10-12",
                "entityName": "ENOC Retail",
                "description": "Expense EXP-0001: Fuel",
                "reference": "RCPT-441",
                "expenseId": "EXP-0001",
                "drAcc": "6800 Travel & Entertainment",
                "crAcc": "1005 Bank",
                "subtotal": "200.00",
                "tax": "0.00",
                "total": "200.00",
                "emirate": "Dubai",
                "vatTreatment": "standard",
            },
            {
                "id": "sup-manual-1",
                "type": "supplier",
                "status": "paid",
                "date": "2026-10-15",
                "invoiceNum": "BILL-9001",
                "entityName": "Acme Cloud",
                "description": "Cloud Hosting",
                "account": "6200 Software & SaaS",
                "subtotal": "1000.00",
                "discount": "0.00",
                "tax": "50.00",
                "total": "1050.00",
                "items": [
                    {
                        "description": "Cloud Compute Oct",
                        "account": "6200 Software & SaaS",
                        "qty": 1,
                        "unitPrice": "1000.00",
                        "amount": "1000.00",
                        "tax": "50.00",
                        "total": "1050.00",
                    }
                ],
            },
        ]
        server, port, handle_api = _start_test_server(entries=entries)
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, executable_path="/usr/bin/chromium")
                _ctx, page, page_errors = _open_authenticated_app(browser, port, handle_api)

                page.evaluate('() => window.switchView("view-ledger")')
                page.wait_for_timeout(200)

                # Both rows (without attached files) must have a visible View button
                exp_row = page.locator("#historyBody tr", has_text="ENOC Retail")
                self.assertEqual(exp_row.locator("button", has_text="View").count(), 1)
                exp_row.locator("button", has_text="View").click()
                page.wait_for_timeout(150)

                exp_modal = page.evaluate(
                    """() => ({
                        display: document.getElementById('invoiceModal').style.display,
                        text: document.getElementById('modalBody').innerText,
                    })"""
                )
                self.assertEqual(exp_modal["display"], "flex")
                self.assertIn("ENOC Retail", exp_modal["text"])
                self.assertIn("6800 Travel & Entertainment", exp_modal["text"])
                self.assertIn("1005 Bank", exp_modal["text"])
                self.assertIn("200.00", exp_modal["text"])

                page.evaluate("() => { document.getElementById('invoiceModal').style.display = 'none'; }")

                # Supplier row without file must also open detailed entry preview including line items
                sup_row = page.locator("#historyBody tr", has_text="BILL-9001")
                self.assertEqual(sup_row.locator("button", has_text="View").count(), 1)
                sup_row.locator("button", has_text="View").click()
                page.wait_for_timeout(150)

                sup_modal = page.evaluate(
                    """() => ({
                        display: document.getElementById('invoiceModal').style.display,
                        text: document.getElementById('modalBody').innerText,
                    })"""
                )
                self.assertEqual(sup_modal["display"], "flex")
                self.assertIn("Acme Cloud", sup_modal["text"])
                self.assertIn("Cloud Compute Oct", sup_modal["text"])
                self.assertIn("1,050.00", sup_modal["text"])

                # Status filter must work accurately even with the View button inside the Status cell
                page.evaluate("() => { document.getElementById('invoiceModal').style.display = 'none'; }")
                page.select_option("#filterStatus", "Paid")
                page.wait_for_timeout(100)
                visible_rows = page.evaluate(
                    """() => Array.from(document.querySelectorAll('#historyBody tr'))
                        .filter(r => r.style.display !== 'none')
                        .map(r => r.innerText)"""
                )
                self.assertEqual(len(visible_rows), 1)
                self.assertIn("Acme Cloud", visible_rows[0])

                self.assertEqual(page_errors, [])
                browser.close()
        finally:
            server.shutdown()
            server.server_close()

    def test_supplier_bills_supports_manual_input_like_sales_invoice(self) -> None:
        suppliers = [
            {"id": "s-1", "name": "Emirates Tech Supplies", "trn": "100123456700003", "address": "Dubai Internet City", "phone": "+971501234567"}
        ]
        server, port, handle_api = _start_test_server(suppliers=suppliers)
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, executable_path="/usr/bin/chromium")
                _ctx, page, page_errors = _open_authenticated_app(browser, port, handle_api)

                page.evaluate('() => window.switchView("view-supplier")')
                page.wait_for_timeout(200)

                # Manual supplier bill form (#resultCard) must be immediately visible without uploading a file
                is_visible = page.locator("#resultCard").is_visible()
                self.assertTrue(is_visible, "Supplier bill form should be visible for manual entry without file upload")

                # Selecting a known supplier from supplierList should auto-fill TRN
                page.fill("#resInvoiceNum", "SUP-2026-088")
                page.fill("#resDate", "2026-11-17")
                page.fill("#resEntity", "Emirates Tech Supplies")
                page.dispatch_event("#resEntity", "input")
                page.wait_for_timeout(100)
                self.assertEqual(page.input_value("#resTrn"), "100123456700003")

                # Should be able to add line items manually via + Add Line Item button
                add_btn = page.locator("#addSupplierLineItemBtn")
                self.assertTrue(add_btn.is_visible(), "Expected + Add Line Item button in Supplier Bills")
                initial_rows = page.locator("#supplierLineItems .line-item-row").count()
                self.assertGreaterEqual(initial_rows, 1)

                # Fill first line item and verify 5% VAT and Total auto-calculate
                first_row = page.locator("#supplierLineItems .line-item-row").first
                first_row.locator(".item-account").fill("6200 Software & SaaS")
                first_row.locator(".item-desc").fill("Annual License")
                first_row.locator(".item-qty").fill("2")
                first_row.locator(".item-price").fill("500")
                page.wait_for_timeout(100)

                add_btn.click()
                page.wait_for_timeout(100)
                self.assertEqual(page.locator("#supplierLineItems .line-item-row").count(), initial_rows + 1)
                second_row = page.locator("#supplierLineItems .line-item-row").nth(1)
                second_row.locator(".item-account").fill("6000 Office Supplies")
                second_row.locator(".item-desc").fill("Printer Paper")
                second_row.locator(".item-qty").fill("1")
                second_row.locator(".item-price").fill("200")
                page.wait_for_timeout(100)

                self.assertEqual(page.input_value("#resSubtotal"), "1,200.00")
                self.assertEqual(page.input_value("#resTax"), "60.00")
                self.assertEqual(page.input_value("#resTotal"), "1,260.00")

                # Save manually entered supplier bill
                page.click("#confirmSaveSupplierBtn")
                page.wait_for_timeout(200)

                saved = page.evaluate(
                    """() => JSON.parse(localStorage.getItem('bookkeeping_history_v2') || '[]')"""
                )
                self.assertEqual(len(saved), 1)
                self.assertEqual(saved[0]["type"], "supplier")
                self.assertEqual(saved[0]["invoiceNum"], "SUP-2026-088")
                self.assertEqual(saved[0]["entityName"], "Emirates Tech Supplies")
                self.assertEqual(saved[0]["total"], "1260.00")
                self.assertEqual(len(saved[0]["items"]), 2)

                self.assertEqual(page_errors, [])
                browser.close()
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
