"""Unit and browser tests for USD->AED FX auto-conversion, Basic plan AI gating, Lumy AI assistant, and backend AI plan enforcement."""

from __future__ import annotations

import base64
from http.server import ThreadingHTTPServer
import json
import os
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import agy_service
from features.support_server import BookkeepingRequestHandler
from state_repository import LumenStateRepository
from tests.browser_shim import sync_playwright
from tests.test_banking_and_menu_new_tab import _open_authenticated_app, _start_test_server


class TestFxConversionAndPlanAiGating(unittest.TestCase):
    """Verify USD->AED 3.675 auto-conversion across all scanner flows, Basic AI locks, Lumy AI widget, and server-side plan enforcement."""

    def test_backend_prediction_enforces_plan_ai_eligibility(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = LumenStateRepository(os.path.join(tmpdir, "state.db"))
            repo.mutate_state(
                {
                    "lumen_accounts": json.dumps(
                        {
                            "acc-basic": {"id": "acc-basic", "email": "basic@co.ae", "plan": "basic", "status": "active", "aiAddon": False},
                            "acc-addon": {"id": "acc-addon", "email": "addon@co.ae", "plan": "basic", "status": "active", "aiAddon": True},
                            "acc-adv": {"id": "acc-adv", "email": "adv@co.ae", "plan": "advance", "status": "active", "aiAddon": False},
                        }
                    )
                }
            )
            server = ThreadingHTTPServer(("127.0.0.1", 0), agy_service.AgyPredictionHandler)
            port = server.server_address[1]
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                with patch.object(agy_service, "get_state_repo", return_value=repo), patch.object(
                    agy_service, "run_agy_prediction", return_value={"text": "OK"}
                ) as mock_run:
                    # 1. Basic plan account without AI add-on must be rejected with HTTP 403
                    req_basic = Request(
                        f"http://127.0.0.1:{port}/api/v1/prediction/test",
                        data=json.dumps({"question": "Summarize my books", "uploads": []}).encode("utf-8"),
                        headers={
                            "Content-Type": "application/json",
                            "X-Lumen-Client": "lumen-bookkeeping-web",
                            "X-Lumen-Account": "acc-basic",
                        },
                        method="POST",
                    )
                    with self.assertRaises(HTTPError) as ctx:
                        urlopen(req_basic, timeout=5)
                    self.assertEqual(ctx.exception.code, 403)
                    err_payload = json.loads(ctx.exception.read().decode("utf-8"))
                    self.assertEqual(err_payload["error"]["code"], "plan_upgrade_required")
                    self.assertEqual(mock_run.call_count, 0)

                    # 2. Basic plan account WITH admin-granted aiAddon=True is permitted
                    req_addon = Request(
                        f"http://127.0.0.1:{port}/api/v1/prediction/test",
                        data=json.dumps({"question": "Summarize my books", "uploads": []}).encode("utf-8"),
                        headers={
                            "Content-Type": "application/json",
                            "X-Lumen-Client": "lumen-bookkeeping-web",
                            "X-Lumen-Account": "acc-addon",
                        },
                        method="POST",
                    )
                    with urlopen(req_addon, timeout=5) as resp:
                        self.assertEqual(resp.status, 200)
                    self.assertEqual(mock_run.call_count, 1)

                    # 3. Advance plan account is permitted
                    req_adv = Request(
                        f"http://127.0.0.1:{port}/api/v1/prediction/test",
                        data=json.dumps({"question": "Summarize my books", "uploads": []}).encode("utf-8"),
                        headers={
                            "Content-Type": "application/json",
                            "X-Lumen-Client": "lumen-bookkeeping-web",
                            "X-Lumen-Account": "acc-adv",
                        },
                        method="POST",
                    )
                    with urlopen(req_adv, timeout=5) as resp:
                        self.assertEqual(resp.status, 200)
                    self.assertEqual(mock_run.call_count, 2)
            finally:
                server.shutdown()
                server.server_close()

    def test_usd_invoices_autoconvert_to_aed_across_sales_supplier_expenses_and_petty_cash(self) -> None:
        tiny_png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        )
        png_file = [{"name": "usd_invoice.png", "mimeType": "image/png", "buffer": tiny_png}]
        server_state = {
            "lumen_accounts": json.dumps([{"id": "owner", "role": "owner", "plan": "advance"}]),
            "bookkeeping_history_v2": "[]",
            "bookkeeping_settings": "{}",
            "bookkeeping_currencies": "[]",
        }

        def handle_api(route):
            url = route.request.url
            if "/api/v1/prediction/" in url:
                body = json.loads(route.request.post_data or "{}")
                q = str(body.get("question") or "")
                if "CUSTOMER INVOICE" in q:
                    reply = json.dumps(
                        {
                            "isValidInvoice": True,
                            "date": "2026-10-15",
                            "dueDate": "2026-11-14",
                            "invoiceNum": "CUST-USD-88",
                            "entityName": "Delta US LLC",
                            "currency": "USD",
                            "items": [{"description": "Advisory", "qty": 1, "unitPrice": 100, "amount": 100, "tax": 5}],
                            "subtotal": 100,
                            "tax": 5,
                            "total": 105,
                        }
                    )
                elif "SUPPLIER INVOICE" in q:
                    reply = json.dumps(
                        {
                            "isValidInvoice": True,
                            "date": "2026-10-15",
                            "invoiceNum": "SUP-USD-77",
                            "entityName": "Global Vendor US",
                            "currency": "USD",
                            "items": [{"description": "Cloud Server", "qty": 1, "unitPrice": 100, "amount": 100, "tax": 5}],
                            "subtotal": 100,
                            "tax": 5,
                            "total": 105,
                        }
                    )
                elif "Petty Cash Receipts" in q:
                    reply = json.dumps(
                        [
                            {
                                "date": "2026-10-15",
                                "reference": "PC-USD-1",
                                "description": "Taxi & Parking US",
                                "tax": "0",
                                "total": "100",
                                "debitAccount": "6800 Travel & Entertainment",
                                "category": "OpEx",
                                "currency": "USD",
                            }
                        ]
                    )
                else:
                    reply = json.dumps(
                        {
                            "isValidInvoice": True,
                            "date": "2026-10-15",
                            "reference": "EXP-USD-7",
                            "entityName": "AWS US",
                            "description": "Cloud compute",
                            "account": "6200 Software & SaaS",
                            "subtotal": 200,
                            "tax": 0,
                            "total": 200,
                            "currency": "USD",
                            "paymentMethod": "Bank",
                        }
                    )
                route.fulfill(status=200, content_type="application/json", body=json.dumps({"text": reply}))
            elif "/api/v1/state" in url:
                route.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": True, "state": server_state}))
            else:
                route.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": True}))

        server, port = _start_test_server()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, executable_path="/usr/bin/chromium")
                _ctx, page, page_errors, console_errors = _open_authenticated_app(browser, port, handle_api)

                # 1. Sales Invoice manual USD -> auto-converted AED (* 3.675) in form & saved ledger entry
                page.evaluate('() => window.switchView("view-customer")')
                page.wait_for_function('() => Boolean(document.querySelector("#custCurrency option[value=\\"USD\\"]"))')
                page.select_option("#custCurrency", "USD")
                page.fill("#custEntity", "US SaaS Buyer Inc")
                page.locator("#custLineItemsList .item-desc").first.fill("Annual License")
                page.locator("#custLineItemsList .item-qty").first.fill("2")
                page.locator("#custLineItemsList .item-rate").first.fill("100")
                page.evaluate('() => { if (typeof window.calcCustTotals === "function") window.calcCustTotals(); }')
                page.wait_for_timeout(100)

                self.assertEqual(page.locator("#custSubtotalDisplay").inner_text().strip(), "735.00")
                self.assertEqual(page.locator("#custVatDisplay").inner_text().strip(), "36.75")
                self.assertEqual(page.locator("#custTotalDisplay").inner_text().strip(), "771.75")
                fx_note = page.locator("#custFxConversionNote").inner_text().strip()
                self.assertIn("Auto-converted from USD 210.00 to AED 771.75 (Rate: 3.675)", fx_note)
                self.assertIn("Rate (USD)", page.locator("#custLineItemsList .cust-rate-label").first.inner_text())

                shot_path = os.environ.get("USD_SCREENSHOT_PATH", "")
                if shot_path:
                    page.locator("#view-customer").screenshot(path=shot_path)

                page.click('#customerInvoiceForm button[type="submit"]')
                page.wait_for_timeout(150)
                saved_inv = page.evaluate('() => JSON.parse(localStorage.getItem("bookkeeping_history_v2") || "[]")[0]')
                self.assertEqual(saved_inv["currency"], "USD")
                self.assertAlmostEqual(float(saved_inv["fxRate"]), 3.675, places=3)
                self.assertEqual(saved_inv["originalTotal"], "210.00")
                self.assertEqual(saved_inv["subtotal"], "735.00")
                self.assertEqual(saved_inv["tax"], "36.75")
                self.assertEqual(saved_inv["total"], "771.75")

                # 2. PDF parser & Customer AI upload auto-detect USD and convert to AED
                parsed_pdf = page.evaluate(
                    """() => window.parseInvoicePdfText(
                        'TAX INVOICE Invoice #: US-CUST-99 Invoice Date: 2026-10-15 Customer Name: Acme US Corp ' +
                        '# Description Qty Rate Taxable Amount Tax Amount 1 Cloud Suite 1 100.00 100.00 5.00 105.00 Total USD: $105.00'
                    )"""
                )
                self.assertIsNotNone(parsed_pdf)
                self.assertEqual(parsed_pdf["currency"], "USD")
                self.assertEqual(parsed_pdf["total"], 105)

                page.evaluate('() => window.switchView("view-customer")')
                page.wait_for_timeout(100)
                page.locator("#custFileInput").set_input_files(png_file)
                page.wait_for_function('() => document.getElementById("custEntity")?.value === "Delta US LLC"')
                self.assertEqual(page.input_value("#custCurrency"), "USD")
                self.assertEqual(page.locator("#custSubtotalDisplay").inner_text().strip(), "367.50")
                self.assertEqual(page.locator("#custVatDisplay").inner_text().strip(), "18.38")
                self.assertEqual(page.locator("#custTotalDisplay").inner_text().strip(), "385.88")

                # 3. Supplier Bill uploaded USD converts at 3.675 even when bookkeeping_currencies was empty
                page.evaluate('() => window.switchView("view-supplier")')
                page.wait_for_timeout(100)
                page.locator("#fileInput").set_input_files(png_file)
                page.wait_for_timeout(100)
                page.locator("#processBtn").click()
                page.wait_for_function('() => document.getElementById("resEntity")?.value === "Global Vendor US"')
                self.assertEqual(page.input_value("#resCurrency"), "USD")
                self.assertEqual(page.input_value("#resSubtotal"), "367.50")
                self.assertEqual(page.input_value("#resTax"), "18.38")
                self.assertEqual(page.input_value("#resTotal"), "385.88")

                # 4. Expense uploaded USD converts at 3.675 to AED
                page.evaluate('() => window.switchView("view-expense")')
                page.wait_for_timeout(100)
                page.locator("#expFileInput").set_input_files(png_file)
                page.wait_for_function('() => document.getElementById("expPayee")?.value === "AWS US"')
                self.assertEqual(page.input_value("#expAmount"), "735.00")
                self.assertEqual(page.input_value("#expVat"), "0.00")
                self.assertIn("converted from USD at 3.675", page.locator("#expAiBanner").inner_text())

                # 5. Petty Cash uploaded USD receipt converts at 3.675 to 367.50 AED
                page.evaluate('() => window.switchView("view-journal")')
                page.wait_for_timeout(100)
                page.locator("#journalFileInput").set_input_files(png_file)
                page.wait_for_timeout(100)
                page.locator("#btnProcessJournalFile").click()
                page.wait_for_function('() => document.getElementById("pettyCashGrandTotal")?.textContent === "367.50"')
                self.assertEqual(page.locator("#pettyCashGrandTotal").inner_text().strip(), "367.50")

                self.assertEqual(page_errors, [])
                self.assertEqual(console_errors, [])
                browser.close()
        finally:
            server.shutdown()
            server.server_close()

    def test_welcome_basic_ai_locked_and_dashboard_assistant_addon_service(self) -> None:
        tiny_png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        )
        png_file = [{"name": "inv.png", "mimeType": "image/png", "buffer": tiny_png}]
        accounts_map = {
            "acc-basic": {"id": "acc-basic", "email": "basic@co.ae", "companyName": "Basic Co LLC", "plan": "basic", "status": "active", "aiAddon": False},
            "acc-advance": {"id": "acc-advance", "email": "adv@co.ae", "companyName": "Advance Co LLC", "plan": "advance", "status": "active", "aiAddon": False},
            "acc-addon": {"id": "acc-addon", "email": "addon@co.ae", "companyName": "AddOn Co LLC", "plan": "basic", "status": "active", "aiAddon": True},
        }
        profiles_list = [
            {"id": "p-basic", "name": "Basic Co LLC", "accountId": "acc-basic", "plan": "basic"},
            {"id": "p-adv", "name": "Advance Co LLC", "accountId": "acc-advance", "plan": "advance"},
            {"id": "p-addon", "name": "AddOn Co LLC", "accountId": "acc-addon", "plan": "basic"},
        ]
        sample_history = [
            {"id": "inv-1", "date": "2026-10-10", "type": "customer", "status": "posted", "invoiceNum": "INV-101", "entityName": "Palm Client", "subtotal": "2000.00", "tax": "100.00", "total": "2100.00"}
        ]
        server_state = {
            "lumen_accounts": json.dumps(accounts_map),
            "lumen_profiles": json.dumps(profiles_list),
            "profile:p-basic::bookkeeping_history_v2": "[]",
            "profile:p-adv::bookkeeping_history_v2": json.dumps(sample_history),
            "profile:p-addon::bookkeeping_history_v2": json.dumps(sample_history),
        }
        ai_requests: list[str] = []

        def handle_api(route):
            url = route.request.url
            if "/api/v1/prediction/" in url:
                body = json.loads(route.request.post_data or "{}")
                ai_requests.append(str(body.get("question") or ""))
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps({"text": "Your revenue is AED 2,000.00 and VAT collected is AED 100.00."}),
                )
            elif "/api/v1/state" in url:
                route.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": True, "state": server_state}))
            else:
                route.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": True}))

        server, port = _start_test_server()
        shot_dir = os.environ.get("SCREENSHOT_DIR", "")
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, executable_path="/usr/bin/chromium")
                ctx = browser.new_context(viewport={"width": 1440, "height": 900})
                ctx.route("**/api/v1/**", handle_api)
                page = ctx.new_page()
                page_errors: list[str] = []
                console_errors: list[str] = []
                page.on("pageerror", lambda e: page_errors.append(str(e)))
                page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

                # 1. Welcome page shows only the 6 core manual items in Basic and Lumy AI Books Assistant in Advance
                page.goto(f"http://127.0.0.1:{port}/welcome.html", wait_until="domcontentloaded")
                page.wait_for_function('() => document.querySelectorAll("#plans article.plan").length === 3')
                basic_card = page.locator("#plans article.plan:has(#btnChoose-basic)")
                basic_items = [t.strip() for t in basic_card.locator(".plan-features li").all_inner_texts()]
                self.assertEqual(
                    basic_items,
                    [
                        "1 company profile",
                        "Income & expense tracking",
                        "VAT-compliant tax invoices",
                        "Customer & supplier contacts",
                        "Manual bank statement entry",
                        "Profit & loss and balance sheet",
                    ],
                )
                advance_card = page.locator("#plans article.plan:has(#btnChoose-advance)")
                self.assertIn("Lumy AI · Dashboard Books Assistant", advance_card.inner_text())
                self.assertEqual(page.locator("#addonServices").count(), 0)
                if shot_dir:
                    page.screenshot(path=os.path.join(shot_dir, "welcome_plans_addon.png"), full_page=True)

                # 2. Basic plan: Dashboard Lumy AI launcher locked + AI extraction boxes locked across views
                page.evaluate(
                    """() => {
                        sessionStorage.setItem('lumen_current_account', 'acc-basic');
                        sessionStorage.setItem('lumen_active_profile', 'p-basic');
                        sessionStorage.setItem('lumen_session_token', 'tok_basic');
                    }"""
                )
                page.goto(f"http://127.0.0.1:{port}/index.html", wait_until="domcontentloaded")
                page.wait_for_function('() => Boolean(window.LumenPlanGate && document.getElementById("lumyAiLockedLauncher"))')

                locked_pill = page.locator("#lumyAiLockedLauncher")
                self.assertTrue(locked_pill.is_visible())
                self.assertIn("Lumy AI · Advance", locked_pill.inner_text())
                self.assertEqual(page.locator("#lumenAiAssistantCard").count(), 0)
                locked_pill.click()
                page.wait_for_selector(".lumen-dialog", timeout=3000)
                self.assertIn("Basic", page.locator(".lumen-dialog").inner_text())
                page.locator('.lumen-dialog [data-dialog-action="cancel"]').click()

                for view_id, box_id in (
                    ("view-supplier", "uploadBox"),
                    ("view-customer", "custUploadBox"),
                    ("view-expense", "expUploadBox"),
                    ("view-bank", "bankUploadBox"),
                    ("view-journal", "journalUploadBox"),
                ):
                    page.evaluate(f'() => window.switchView("{view_id}")')
                    page.wait_for_timeout(120)
                    self.assertTrue(page.locator(f'[data-testid="ai-lock-{box_id}"]').is_visible())
                    self.assertIn("is-ai-locked", page.locator(f"#{box_id}").get_attribute("class") or "")
                    self.assertEqual(page.locator("#lumyFloatingRoot").count(), 0)

                # Attempting AI upload on Basic is blocked and shows upgrade prompt instead of hitting AI
                page.evaluate('() => window.switchView("view-customer")')
                page.wait_for_timeout(100)
                page.locator("#custFileInput").set_input_files(png_file)
                page.wait_for_selector(".lumen-dialog", timeout=3000)
                self.assertIn("Basic", page.locator(".lumen-dialog").inner_text())
                page.locator('.lumen-dialog [data-dialog-action="cancel"]').click()
                page.wait_for_timeout(100)
                self.assertEqual(len(ai_requests), 0, "Basic plan must not invoke AI extraction endpoint")

                # 2b. Basic plan with admin-enabled aiAddon=True unlocks canUseAi()
                page.evaluate(
                    """() => {
                        sessionStorage.setItem('lumen_current_account', 'acc-addon');
                        sessionStorage.setItem('lumen_active_profile', 'p-addon');
                    }"""
                )
                page.goto(f"http://127.0.0.1:{port}/index.html", wait_until="domcontentloaded")
                page.wait_for_function('() => Boolean(document.getElementById("lumenAiAssistantCard"))')
                self.assertTrue(page.evaluate("() => window.LumenPlanGate.canUseAi()"))

                # 3. Advance plan: Lumen/Lumy AI floats as a chatbox on lower right of Dashboard by default
                page.evaluate(
                    """() => {
                        sessionStorage.setItem('lumen_current_account', 'acc-advance');
                        sessionStorage.setItem('lumen_active_profile', 'p-adv');
                    }"""
                )
                page.goto(f"http://127.0.0.1:{port}/index.html", wait_until="domcontentloaded")
                page.wait_for_function('() => Boolean(document.getElementById("lumenAiAssistantCard"))')
                self.assertTrue(page.locator("#lumenAiAssistantCard").is_visible())
                self.assertEqual(page.locator("#lumenAiAssistantCard").get_attribute("data-addon-locked"), "false")
                self.assertIn("Lumy AI · Books Assistant", page.locator("#lumenAiAssistantCard .lumy-chat-title").inner_text())
                self.assertGreaterEqual(page.locator("#lumenAiAssistantCard svg").count(), 1)

                # Hidden when switching off Dashboard
                page.evaluate('() => window.switchView("view-ledger")')
                page.wait_for_timeout(120)
                self.assertEqual(page.locator("#lumyFloatingRoot").count(), 0)

                # Visible again on Dashboard -> chat, minimize to launcher pill, and pop back out
                page.evaluate('() => window.switchView("view-dashboard")')
                page.wait_for_function('() => Boolean(document.getElementById("lumenAiAssistantCard"))')
                page.fill("#lumenAiInput", "How much VAT and revenue do I have?")
                page.click("#btnSendLumenAi")
                page.wait_for_function('() => (document.getElementById("lumenAiMessages")?.innerText || "").includes("AED 2,000.00")')
                self.assertGreaterEqual(len(ai_requests), 1)
                self.assertIn("Revenue: 2,000.00", ai_requests[-1])
                if shot_dir:
                    page.locator("#lumenAiAssistantCard").screenshot(path=os.path.join(shot_dir, "dashboard_lumy_popup.png"))

                # Minimizes to floating pill and re-opens
                page.click("#btnCloseLumyChat")
                page.wait_for_function('() => Boolean(document.getElementById("lumyAiLauncher"))')
                self.assertEqual(page.locator("#lumenAiAssistantCard").count(), 0)
                page.click("#lumyAiLauncher")
                page.wait_for_function('() => Boolean(document.getElementById("lumenAiAssistantCard"))')

                self.assertEqual(page_errors, [])
                self.assertEqual(console_errors, [])
                browser.close()
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
