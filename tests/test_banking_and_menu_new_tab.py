"""E2E tests for Banking re-upload, monthly dashboard split, editing, ledger Bank label, manual entry, menu new-tab, and timesheet collapse."""

from __future__ import annotations

from http.server import ThreadingHTTPServer
import json
import threading
import unittest

from features.support_server import BookkeepingRequestHandler
from tests.browser_shim import sync_playwright


def _start_test_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), BookkeepingRequestHandler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, port


def _open_authenticated_app(browser, port: int, handle_api):
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    ctx.route("**/api/v1/**", handle_api)
    page = ctx.new_page()
    page_errors: list[str] = []
    console_errors: list[str] = []
    page.on("pageerror", lambda e: page_errors.append(str(e)))
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

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
        '() => typeof window.switchView === "function" && typeof window.renderBankDashboard === "function" && typeof window.initBankForm === "function"'
    )
    return ctx, page, page_errors, console_errors


class TestBankingAndMenuNewTab(unittest.TestCase):
    """Verify banking workflows, menu new-tab navigation (with popup-block fallback), and timesheet collapse."""

    def test_bank_reupload_manual_entry_monthly_split_edit_ledger_label_and_menu_new_tab(self) -> None:
        ai_calls: list[str] = []
        server_state: dict[str, str] = {
            "lumen_accounts": json.dumps([{"id": "owner", "role": "owner", "plan": "advance"}]),
            "bookkeeping_history_v2": "[]",
            "bookkeeping_bank_statements": "[]",
            "bookkeeping_settings": "{}",
        }

        def handle_api(route):
            url = route.request.url
            if "/api/v1/state" in url:
                if route.request.method == "POST":
                    try:
                        payload = json.loads(route.request.post_data or "{}")
                        for k, v in (payload.get("set") or {}).items():
                            server_state[k] = str(v)
                        for k in payload.get("remove") or []:
                            server_state.pop(k, None)
                    except Exception:
                        pass
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps({"ok": True, "state": server_state}),
                )
            elif "/api/v1/prediction/" in url:
                post_data = route.request.post_data or ""
                ai_calls.append(post_data)
                if len(ai_calls) == 1:
                    payload = {
                        "isValidStatement": True,
                        "bankName": "First Abu Dhabi Bank",
                        "accountNumber": "FAB-001",
                        "openingBalance": 0.00,
                        "transactions": [
                            {
                                "date": "2026-09-15",
                                "description": "Initial Deposit",
                                "amount": 1200.00,
                                "account": "4100 Service Revenue",
                                "type": "deposit",
                            }
                        ],
                    }
                else:
                    payload = {
                        "isValidStatement": True,
                        "bankName": "ADCB Corporate",
                        "accountNumber": "ADCB-999",
                        "openingBalance": 1100.00,
                        "transactions": [
                            {
                                "date": "2026-09-25",
                                "description": "Late Month Transfer",
                                "amount": 1500.00,
                                "account": "4100 Service Revenue",
                                "type": "deposit",
                            },
                            {
                                "date": "12/09/2026",
                                "description": "Client Transfer",
                                "amount": 2000.00,
                                "account": "4100 Service Revenue",
                                "type": "deposit",
                            },
                            {
                                "date": "2026-09-05",
                                "description": "Opening Utility Payment",
                                "amount": 100.00,
                                "account": "6000 Office Supplies",
                                "type": "withdrawal",
                            },
                        ],
                    }
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps({"text": f"```json\n{json.dumps(payload)}\n```"}),
                )
            else:
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps({"ok": True}),
                )

        server, port = _start_test_server()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, executable_path="/usr/bin/chromium")
                ctx, page, page_errors, console_errors = _open_authenticated_app(browser, port, handle_api)

                # 6a. Menu links have real hash hrefs, NO arrow button, and switch views in the same tab on normal click
                self.assertEqual(page.locator(".nav-new-tab-btn").count(), 0, "Hover arrow button should be removed")
                bank_nav = page.locator('a.nav-item[data-target="view-bank"]')
                self.assertEqual(bank_nav.get_attribute("href"), "#view-bank")
                pages_before_click = len(ctx.pages)
                bank_nav.click()
                page.wait_for_function(
                    '() => typeof window.switchView === "function" && document.getElementById("view-bank")?.classList.contains("active")'
                )
                self.assertEqual(len(ctx.pages), pages_before_click, "Normal menu click should switch view in the same tab without opening a new tab")
                self.assertTrue(page.locator("#view-bank").is_visible(), "Clicking Banking menu did not activate view-bank in the current tab")
                page.evaluate('() => { window.switchView("view-dashboard"); }')
                page.wait_for_timeout(100)

                # Also verify Ctrl/Meta+Click opens in a new tab
                ledger_nav = page.locator('a.nav-item[data-target="view-ledger"]')
                with ctx.expect_page() as ctrl_tab_info:
                    ledger_nav.click(modifiers=["Control"], force=True)
                ctrl_tab = ctrl_tab_info.value
                ctrl_tab.wait_for_function(
                    '() => typeof window.switchView === "function" && document.getElementById("view-ledger")?.classList.contains("active")'
                )
                self.assertTrue(ctrl_tab.locator("#view-ledger").is_visible(), "Ctrl+Click new tab did not activate view-ledger")
                ctrl_tab.close()

                # Switch main test page into Banking for form & upload checks
                page.evaluate('() => window.switchView("view-bank")')
                page.wait_for_timeout(200)

                # 5. Manual entry form (#bankResultCard) is visible immediately without file upload
                self.assertTrue(page.locator("#bankResultCard").is_visible())
                self.assertGreaterEqual(page.locator("#bankTransactionsBody tr").count(), 1)

                # 1. Test upload + Re-upload of bank statement
                csv_1 = "Date,Description,Amount\n2026-09-15,Initial Deposit,1200.00\n"
                page.set_input_files(
                    "#bankFile",
                    {"name": "stmt1.csv", "mimeType": "text/csv", "buffer": csv_1.encode("utf-8")},
                )
                page.wait_for_timeout(100)
                self.assertTrue(page.locator("#processBankBtn").is_visible())
                page.click("#processBankBtn")
                page.wait_for_function('() => document.getElementById("resBankName")?.value === "First Abu Dhabi Bank"')
                self.assertEqual(page.input_value("#resBankBalance"), "0.00")
                self.assertEqual(page.input_value("#resBankEndingBalance"), "1200.00")

                # Click Re-upload — must NOT throw and must reset upload box + form
                page.click("#reuploadBankBtn")
                page.wait_for_timeout(150)
                self.assertEqual(page_errors, [], f"Re-upload threw page error: {page_errors}")
                self.assertTrue(page.locator("#bankUploadBox").is_visible())
                self.assertFalse(page.locator("#bankFilePreview").is_visible())
                self.assertEqual(page.input_value("#resBankName"), "")
                self.assertEqual(page.input_value("#bankFile"), "")

                # Re-upload a second statement and verify transactions are sorted OLDEST -> NEWEST and Ending = Beginning + txns
                csv_2 = "Date,Description,Amount\n2026-09-25,Late Month Transfer,1500.00\n12/09/2026,Client Transfer,2000.00\n2026-09-05,Opening Utility Payment,-100.00\n"
                page.set_input_files(
                    "#bankFile",
                    {"name": "stmt2.csv", "mimeType": "text/csv", "buffer": csv_2.encode("utf-8")},
                )
                page.wait_for_timeout(100)
                page.click("#processBankBtn")
                page.wait_for_function('() => document.getElementById("resBankName")?.value === "ADCB Corporate"')
                self.assertEqual(page.input_value("#resBankBalance"), "1100.00")
                self.assertEqual(page.input_value("#resBankEndingBalance"), "4500.00")
                self.assertEqual(len(ai_calls), 2)
                self.assertIn("Client Transfer", ai_calls[1])
                uploaded_dates = page.evaluate(
                    '() => Array.from(document.querySelectorAll("#bankTransactionsBody tr input[type=\\"date\\"]")).map(i => i.value)'
                )
                self.assertEqual(uploaded_dates, ["2026-09-05", "2026-09-12", "2026-09-25"], f"Expected oldest-to-newest order, got {uploaded_dates}")
                self.assertEqual(page.input_value("#resBankDate"), "2026-09-25")

                # Reset back to clean manual entry using New Manual Statement button
                page.click("#manualBankBtn")
                page.wait_for_timeout(150)

                # 5 + 2 + Beginning/Ending balance calculation + Bank VAT 5%: Enter manual statement for October 2026
                page.fill("#resBankName", "Emirates NBD")
                page.fill("#resBankAccount", "ENBD-8881")
                page.fill("#resBankMonth", "2026-10")
                page.fill("#resBankDate", "2026-10-31")
                page.fill("#resBankBalance", "0.00")

                first_row = page.locator("#bankTransactionsBody tr").first
                first_row.locator('input[type="date"]').fill("2026-10-10")
                first_row.locator('input[type="text"]').fill("Customer Deposit Oct")
                first_row.locator('input[type="number"].num-col').fill("5000.00")
                first_row.locator("select.account-col").select_option("4100 Service Revenue")

                page.click("#addBankTxnBtn")
                page.wait_for_timeout(100)
                self.assertEqual(page.locator("#bankTransactionsBody tr").count(), 2)
                second_row = page.locator("#bankTransactionsBody tr").nth(1)
                second_row.locator('input[type="date"]').fill("2026-10-20")
                second_row.locator('input[type="text"]').fill("Office Rent Oct")
                second_row.locator('input[type="number"].num-col').fill("-1200.00")
                second_row.locator('input[type="number"].vat-col').fill("5")
                second_row.locator("select.account-col").select_option("6400 Rent Expense")
                page.wait_for_timeout(50)
                self.assertEqual(page.input_value("#resBankEndingBalance"), "3800.00")

                page.click("#confirmSaveBankBtn")
                page.wait_for_timeout(200)

                # Enter a second manual bank statement for November 2026 carrying forward 3800.00 beginning balance
                page.fill("#resBankName", "Emirates NBD")
                page.fill("#resBankAccount", "ENBD-8881")
                page.fill("#resBankMonth", "2026-11")
                page.fill("#resBankDate", "2026-11-30")
                page.fill("#resBankBalance", "3800.00")

                nov_row = page.locator("#bankTransactionsBody tr").first
                nov_row.locator('input[type="date"]').fill("2026-11-05")
                nov_row.locator('input[type="text"]').fill("Retainer Nov")
                nov_row.locator('input[type="number"].num-col').fill("2000.00")
                nov_row.locator("select.account-col").select_option("4100 Service Revenue")
                page.wait_for_timeout(50)
                self.assertEqual(page.input_value("#resBankEndingBalance"), "5800.00")

                page.click("#confirmSaveBankBtn")
                page.wait_for_timeout(200)

                # 2. Verify Bank Accounts Dashboard splits into months (Nov 2026 and Oct 2026)
                dash_rows = page.locator("#bankDashboardBody tr")
                self.assertEqual(dash_rows.count(), 2, "Expected 2 monthly rows in Bank Dashboard")
                self.assertIn("2026-11", dash_rows.nth(0).inner_text())
                self.assertIn("5,800.00", dash_rows.nth(0).inner_text())
                self.assertIn("Beg: 3,800.00", dash_rows.nth(0).inner_text())
                self.assertIn("Reconciled", dash_rows.nth(0).inner_text())
                self.assertIn("2026-10", dash_rows.nth(1).inner_text())
                self.assertIn("3,800.00", dash_rows.nth(1).inner_text())
                self.assertIn("Reconciled", dash_rows.nth(1).inner_text())

                # Filter by month 2026-10
                page.select_option("#bankDashboardMonthFilter", "2026-10")
                page.wait_for_timeout(150)
                self.assertEqual(page.locator("#bankDashboardBody tr").count(), 1)
                self.assertIn("2026-10", page.locator("#bankDashboardBody tr").first.inner_text())
                page.select_option("#bankDashboardMonthFilter", "all")
                page.wait_for_timeout(150)

                # 3. Edit the 2026-10 bank statement directly from Bank Dashboard
                oct_row = page.locator("#bankDashboardBody tr", has_text="2026-10")
                oct_row.locator("button", has_text="Edit").click()
                page.wait_for_timeout(150)
                self.assertEqual(page.evaluate('() => document.getElementById("editBankStatementModal").style.display'), "flex")
                self.assertEqual(page.input_value("#editBankStmtName"), "Emirates NBD")
                self.assertEqual(page.input_value("#editBankStmtMonth"), "2026-10")
                self.assertEqual(page.input_value("#editBankStmtBalance"), "0.00")
                self.assertEqual(page.input_value("#editBankStmtEndingBalance"), "3800.00")
                self.assertEqual(page.locator("#editBankStmtTxnsBody tr").count(), 2)

                deposit_edit_row = page.locator("#editBankStmtTxnsBody tr", has_text="").filter(has=page.locator('input[value="Customer Deposit Oct"]'))
                deposit_edit_row.locator(".edit-stmt-txn-amt").fill("5500.00")
                page.wait_for_timeout(50)
                self.assertEqual(page.input_value("#editBankStmtEndingBalance"), "4300.00")
                page.click("#btnSaveEditedBankStmt")
                page.wait_for_timeout(200)

                self.assertEqual(page.evaluate('() => document.getElementById("editBankStatementModal").style.display'), "none")
                oct_row_after = page.locator("#bankDashboardBody tr", has_text="2026-10")
                self.assertIn("4,300.00", oct_row_after.inner_text())
                self.assertIn("Reconciled", oct_row_after.inner_text())

                # Also add a supplier & customer invoice with VAT so General Ledger VAT column recognition is verified for all 3 types
                page.evaluate(
                    """() => {
                        const hist = JSON.parse(localStorage.getItem('bookkeeping_history_v2') || '[]');
                        hist.unshift({
                            id: 'sup-vat-1', date: '2026-10-22', type: 'supplier', status: 'posted',
                            invoiceNum: 'SUP-VAT-1', entityName: 'Global Vendor LLC', description: 'Cloud Hosting',
                            account: '6200 Software & SaaS', subtotal: '1000.00', discount: '0.00', tax: '50.00', total: '1050.00'
                        });
                        hist.unshift({
                            id: 'cust-vat-1', date: '2026-10-23', type: 'customer', status: 'posted',
                            invoiceNum: 'INV-VAT-1', entityName: 'Acme Client PJSC', description: 'Consulting Retainer',
                            account: '4100 Service Revenue', subtotal: '500.00', discount: '0.00', tax: '25.00', total: '525.00'
                        });
                        localStorage.setItem('bookkeeping_history_v2', JSON.stringify(hist));
                        if (typeof window.LumenProfiles?.flushSync === 'function') window.LumenProfiles.flushSync();
                    }"""
                )
                page.wait_for_timeout(150)

                # 4. Clicking General Ledger switches view in the same tab; check "Bank" Inv # and VAT column
                ledger_nav.click()
                page.wait_for_function(
                    '() => typeof window.loadHistory === "function" && document.getElementById("view-ledger")?.classList.contains("active")'
                )
                page.wait_for_timeout(150)
                ledger_rows = page.locator("#historyBody tr")
                self.assertEqual(ledger_rows.count(), 5)
                bank_inv_cols = [
                    ledger_rows.nth(i).locator("td").nth(1).inner_text().strip()
                    for i in range(ledger_rows.count())
                    if ledger_rows.nth(i).locator("td").nth(2).inner_text().strip() == "Bank"
                ]
                self.assertEqual(bank_inv_cols, ["Bank", "Bank", "Bank"])

                bank_rent_vat = page.locator("#historyBody tr", has_text="Office Rent Oct").locator("td").nth(8).inner_text().strip()
                sup_vat = page.locator("#historyBody tr", has_text="SUP-VAT-1").locator("td").nth(8).inner_text().strip()
                cust_vat = page.locator("#historyBody tr", has_text="INV-VAT-1").locator("td").nth(8).inner_text().strip()
                self.assertEqual(bank_rent_vat, "57.14")
                self.assertEqual(sup_vat, "50.00")
                self.assertEqual(cust_vat, "25.00")

                filter_inv_options = page.evaluate(
                    '() => Array.from(document.getElementById("filterInv")?.options || []).map(o => o.value)'
                )
                self.assertIn("Bank", filter_inv_options)

                # 7. Credit Note in sidebar menu bar opens view-credit-notes cleanly in the same tab
                cn_nav = page.locator('a.nav-item[data-target="view-credit-notes"]')
                self.assertEqual(cn_nav.count(), 1)
                self.assertEqual(cn_nav.inner_text().strip(), "Credit Note")
                self.assertEqual(page.locator("#view-customer #taxCreditNoteCard").count(), 0)
                cn_nav.click()
                page.wait_for_function('() => document.getElementById("view-credit-notes")?.classList.contains("active")')
                self.assertTrue(page.locator("#view-credit-notes #taxCreditNoteCard").is_visible())
                self.assertTrue(page.locator("#view-credit-notes #creditNoteForm").is_visible())
                self.assertTrue(page.locator("#view-credit-notes #salesDocumentsCard").is_visible())

                # 8. Sales Invoice without VAT shows Commercial Invoice & removes "(Art. 59 Line Breakdown)"
                page.evaluate('() => window.switchView("view-customer")')
                page.wait_for_timeout(150)
                self.assertEqual(page.locator("#custLineItemsContainer h4").inner_text().strip(), "Service / Product Details")
                page.fill("#custEntity", "Commercial Buyer LLC")
                page.locator("#custLineItemsList .item-desc").first.fill("Exempt Supply")
                page.locator("#custLineItemsList .item-rate").first.fill("1000")
                page.locator("#custLineItemsList .item-vat-rate").first.select_option("0")
                page.evaluate('() => { const s = document.querySelector("#custLineItemsList .item-vat-rate"); if (s) { s.dataset.userModified = "1"; } if (typeof window.calcCustTotals === "function") window.calcCustTotals(); }')
                page.wait_for_timeout(100)
                self.assertEqual(page.locator("#custDocTypeBadge").inner_text().strip(), "Commercial Invoice")
                self.assertEqual(page.locator("#custInvoiceCardTitle").inner_text().strip(), "Generate Commercial Invoice")
                page.click("#previewInvoiceBtn")
                page.wait_for_selector('#invoiceModal[style*="flex"]', timeout=3000)
                self.assertIn("COMMERCIAL INVOICE", page.locator("#modalBody").inner_text())
                page.click('#invoiceModal button:has-text("Close")')
                page.wait_for_timeout(100)

                page.locator("#custLineItemsList .item-vat-rate").first.select_option("5")
                page.evaluate('() => { if (typeof window.calcCustTotals === "function") window.calcCustTotals(); }')
                page.wait_for_timeout(100)
                self.assertEqual(page.locator("#custDocTypeBadge").inner_text().strip(), "Tax Invoice")
                page.click("#previewInvoiceBtn")
                page.wait_for_selector('#invoiceModal[style*="flex"]', timeout=3000)
                self.assertIn("TAX INVOICE", page.locator("#modalBody").inner_text())
                page.click('#invoiceModal button:has-text("Close")')

                self.assertEqual(page_errors, [], f"Unexpected page errors: {page_errors}")
                self.assertEqual(console_errors, [], f"Unexpected console errors: {console_errors}")
                browser.close()
        finally:
            server.shutdown()
            server.server_close()

    def test_timesheet_top_eosb_bottom_and_collapsible_employee_lists(self) -> None:
        server_state = {
            "lumen_accounts": json.dumps([{"id": "owner", "role": "owner", "plan": "advance"}]),
            "bookkeeping_employees": json.dumps([
                {"empId": "E-01", "name": "Alice Longlist", "basicSalary": 10000, "totalPay": 12000, "dateHired": "2023-01-10"},
                {"empId": "E-02", "name": "Bob Longlist", "basicSalary": 11000, "totalPay": 13000, "dateHired": "2022-05-01"},
            ]),
            "payroll_2026-10": json.dumps({
                "paymentAccount": "1005 Bank",
                "accrueEOSB": True,
                "employees": {
                    "E-01": {"name": "Alice Longlist", "basic": "10,000.00", "allowance": "2,000.00", "totalFixed": "12,000.00", "netPay": 12000},
                    "E-02": {"name": "Bob Longlist", "basic": "11,000.00", "allowance": "2,000.00", "totalFixed": "13,000.00", "netPay": 13000},
                },
            }),
            "bookkeeping_history_v2": "[]",
            "bookkeeping_settings": "{}",
        }

        def handle_api(route):
            if "/api/v1/state" in route.request.url:
                route.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": True, "state": server_state}))
            else:
                route.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": True}))

        server, port = _start_test_server()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, executable_path="/usr/bin/chromium")
                _ctx, page, page_errors, console_errors = _open_authenticated_app(browser, port, handle_api)
                page.evaluate('() => window.switchView("view-timesheet")')
                page.wait_for_function('() => document.querySelectorAll("#savedTimesheetsContainer .ts-period-card").length === 1')

                positions = page.evaluate(
                    """() => {
                        const ts = document.getElementById('timesheetWpsCard')?.getBoundingClientRect();
                        const eosb = document.getElementById('eosbSummaryCard')?.getBoundingClientRect();
                        return { tsTop: ts ? ts.top : -1, eosbTop: eosb ? eosb.top : -1 };
                    }"""
                )
                self.assertLess(positions["tsTop"], positions["eosbTop"], f"Timesheet should appear above EOSB: {positions}")

                self.assertTrue(page.locator("#savedTimesheetsContainer .ts-emp-table-wrap").first.is_visible())
                page.locator("#savedTimesheetsContainer .ts-collapse-toggle").first.click()
                self.assertFalse(page.locator("#savedTimesheetsContainer .ts-emp-table-wrap").first.is_visible())
                self.assertIn("Show Employees (2)", page.locator("#savedTimesheetsContainer .ts-collapse-toggle").first.inner_text())
                page.locator("#btnToggleAllTimesheets").click()
                self.assertTrue(page.locator("#savedTimesheetsContainer .ts-emp-table-wrap").first.is_visible())

                self.assertTrue(page.locator("#eosbEmpTableWrap").is_visible())
                page.locator("#btnToggleEosbEmpTable").click()
                self.assertFalse(page.locator("#eosbEmpTableWrap").is_visible())
                page.locator("#btnToggleEosbEmpTable").click()
                self.assertTrue(page.locator("#eosbEmpTableWrap").is_visible())

                self.assertEqual(page_errors, [])
                self.assertEqual(console_errors, [])
                browser.close()
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
