"""Local static & mock Flowise AI server for Lumen Accounting Suite E2E/BDD tests.

Serves the static application from `APP_SOURCE_DIR` on `localhost:9091` while:
1. Providing local vendor shims (`/__vendor__/chart.js`, `/__vendor__/pdf.min.js`,
   `/__vendor__/fonts.css`) so air-gapped/containerized browser runs never hang
   or log `ERR_CONNECTION_TIMED_OUT` on external CDN requests.
2. Providing a deterministic Flowise AI prediction endpoint
   (`POST /api/v1/prediction/*`) for Supplier Bills, Customer Invoices,
   Petty Cash Receipts, and Bank Statement extraction.
"""

from __future__ import annotations

import json
import mimetypes
import os
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import agy_service
from features.config import APP_SOURCE_DIR, HOST, PORT
from vendor_shims import CHART_JS_SHIM

RECAPTCHA_JS_SHIM = """
(function(window) {
    window.grecaptcha = {
        render: function(el, opts) {
            const container = typeof el === 'string' ? document.getElementById(el) : el;
            if (container) {
                container.innerHTML = '<button type="button" id="recaptchaStubBtn" class="btn btn-outline btn-sm">I\\'m not a robot</button>';
                const btn = container.querySelector('#recaptchaStubBtn');
                if (btn) {
                    btn.addEventListener('click', function() {
                        if (opts && typeof opts.callback === 'function') opts.callback('behave-local-captcha-token');
                    });
                }
            }
            return 1;
        },
        reset: function() {},
        getResponse: function() { return 'behave-local-captcha-token'; }
    };
})(window);
"""

PDF_JS_SHIM = """
(function(window) {
    const pdfjsLib = {
        version: '3.11.174',
        GlobalWorkerOptions: { workerSrc: '' },
        getDocument: function(params) {
            return {
                promise: Promise.resolve({
                    numPages: 1,
                    getPage: function(pageNum) {
                        return Promise.resolve({
                            getViewport: function(opts) {
                                return { width: 600, height: 800, scale: (opts && opts.scale) || 1 };
                            },
                            render: function(renderCtx) {
                                try {
                                    if (renderCtx && renderCtx.canvasContext) {
                                        const ctx = renderCtx.canvasContext;
                                        ctx.fillStyle = '#ffffff';
                                        ctx.fillRect(0, 0, 600, 800);
                                        ctx.fillStyle = '#0f172a';
                                        ctx.font = '16px sans-serif';
                                        ctx.fillText('Mock PDF Document Page ' + pageNum, 40, 60);
                                    }
                                } catch (e) {}
                                return { promise: Promise.resolve() };
                            },
                            getTextContent: function() {
                                return Promise.resolve({
                                    items: [
                                        { str: 'Emirates NBD Statement' },
                                        { str: 'Account: 1029384756' },
                                        { str: '2026-10-15 DEWA Electricity Bill -450.00' },
                                        { str: '2026-10-18 Client Retainer Deposit +5000.00' }
                                    ]
                                });
                            }
                        });
                    }
                })
            };
        }
    };
    window.pdfjsLib = pdfjsLib;
    window['pdfjs-dist/build/pdf'] = pdfjsLib;
})(window);
"""


def build_mock_ai_response(body_text: str) -> dict:
    """Return a deterministic Flowise AI response payload matching the prompt type."""
    if "BANK STATEMENT" in body_text:
        payload = {
            "bankName": "Emirates NBD",
            "accountNumber": "1029384756",
            "closingBalance": 14550.00,
            "transactions": [
                {
                    "date": "2026-10-15",
                    "description": "DEWA Utility Payment",
                    "amount": 450.00,
                    "account": "6100 Utilities",
                    "type": "withdrawal",
                },
                {
                    "date": "2026-10-18",
                    "description": "Client Retainer Receipt",
                    "amount": 5000.00,
                    "account": "4100 Service Revenue",
                    "type": "deposit",
                },
            ],
        }
        return {"text": f"```json\n{json.dumps(payload, indent=2)}\n```"}

    if "Petty Cash Receipts" in body_text:
        payload = [
            {
                "date": "2026-10-12",
                "reference": "PC-901",
                "description": "Stationery & Printer Toner",
                "tax": 10.00,
                "total": 210.00,
                "currency": "AED",
                "account": "6000 Office Supplies",
                "category": "OpEx",
            }
        ]
        return {"text": f"```json\n{json.dumps(payload, indent=2)}\n```"}

    if "EXPENSE RECEIPT" in body_text:
        payload = {
            "date": "2026-10-22",
            "reference": "RCP-ADNOC-7721",
            "entityName": "ADNOC Distribution",
            "vendorTrn": "100234567890003",
            "emirate": "Abu Dhabi",
            "description": "Fleet Fuel & Service",
            "account": "6800 Travel & Entertainment",
            "subtotal": 200.00,
            "tax": 10.00,
            "total": 210.00,
            "currency": "AED",
            "paymentMethod": "Card",
        }
        return {"text": f"```json\n{json.dumps(payload, indent=2)}\n```"}

    if "CUSTOMER INVOICE" in body_text:
        payload = {
            "date": "2026-10-20",
            "invoiceNum": "INV-AI-2001",
            "entityName": "Lumen Management Consultancy",
            "trn": "100445566778803",
            "address": "Business Bay, Dubai, UAE",
            "phone": "+971-4-321-9000",
            "items": [
                {
                    "description": "AI Advisory Services",
                    "qty": 2,
                    "amount": 2500,
                }
            ],
            "subtotal": 5000,
            "tax": 250,
            "total": 5250,
        }
        return {"text": f"```json\n{json.dumps(payload, indent=2)}\n```"}

    # Default: SUPPLIER INVOICE
    if (
        "MFZ-339673" in body_text
        or "application/pdf" in body_text
        or "Extract the supplier invoice JSON directly" in body_text
    ):
        payload = {
            "date": "2026-06-23",
            "invoiceNum": "MFZ-339673",
            "entityName": "Meydan Free Zone",
            "trn": "100027637600003",
            "address": "Meydan Road, Nad Al Sheba, P.O. Box 35195, Dubai, U.A.E.",
            "phone": "800391",
            "items": [
                {
                    "description": "License - New",
                    "qty": 1,
                    "unitPrice": 12125.00,
                    "amount": 12125.00,
                    "tax": 0.00,
                    "account": "6550 Licenses & Permits",
                    "category": "OpEx",
                },
                {
                    "description": "Facility - Co-working shared desk - New",
                    "qty": 1,
                    "unitPrice": 357.14,
                    "amount": 357.14,
                    "tax": 17.86,
                    "account": "6400 Rent Expense",
                    "category": "OpEx",
                },
                {
                    "description": "Innovation Fee",
                    "qty": 1,
                    "unitPrice": 10.00,
                    "amount": 10.00,
                    "tax": 0.00,
                    "account": "6550 Licenses & Permits",
                    "category": "OpEx",
                },
                {
                    "description": "Knowledge Fee",
                    "qty": 1,
                    "unitPrice": 10.00,
                    "amount": 10.00,
                    "tax": 0.00,
                    "account": "6550 Licenses & Permits",
                    "category": "OpEx",
                },
            ],
            "subtotal": 12502.14,
            "discount": 0,
            "tax": 17.86,
            "total": 12520.00,
            "currency": "AED",
        }
        return {"text": f"```json\n{json.dumps(payload, indent=2)}\n```"}

    payload = {
        "date": "2026-10-15",
        "invoiceNum": "SUP-AI-8001",
        "entityName": "Gulf Cloud Infrastructure LLC",
        "trn": "100998877665503",
        "address": "Dubai Internet City, UAE",
        "phone": "+971-4-888-1000",
        "items": [
            {
                "description": "Managed Cloud Compute Cluster",
                "qty": 1,
                "unitPrice": 2000,
                "amount": 2000,
                "tax": 100,
                "account": "6200 Software & SaaS",
                "category": "COGS",
            }
        ],
        "subtotal": 2000,
        "discount": 0,
        "tax": 100,
        "total": 2100,
        "currency": "AED",
    }
    return {"text": f"```json\n{json.dumps(payload, indent=2)}\n```"}


class BookkeepingRequestHandler(BaseHTTPRequestHandler):
    """HTTP handler serving static app files, vendor shims, and mock AI endpoints."""

    def log_message(self, format: str, *args) -> None:
        return  # Silence per-request stdout noise during BDD test runs

    custom_api_handler = None

    def _try_custom_api_handler(self, body_text: str = "") -> bool:
        handler = type(self).custom_api_handler
        if handler is None or not self.path.startswith("/api/v1/"):
            return False
        port = self.server.server_address[1]
        req = type("Req", (), {"url": f"http://127.0.0.1:{port}{self.path}", "method": self.command, "post_data": body_text, "headers": dict(self.headers)})()
        res: dict[str, object] = {"status": 200, "content_type": "application/json; charset=utf-8", "body": "{}"}
        route = type("Route", (), {"request": req, "fulfill": lambda _s, status=200, content_type="application/json", body="{}": res.update({"status": status, "content_type": content_type, "body": body})})()
        handler(route)
        raw = res["body"].encode("utf-8") if isinstance(res["body"], str) else bytes(res["body"])
        self._send_bytes(raw, str(res["content_type"]), status=int(res["status"]))
        return True

    def _send_bytes(self, content: bytes, content_type: str, status: int = 200) -> None:
        try:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(content)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        req_path = parsed.path
        if self._try_custom_api_handler():
            return
        if req_path == "/__vendor__/chart.js":
            return self._send_bytes(CHART_JS_SHIM.encode("utf-8"), "application/javascript; charset=utf-8")
        if req_path in ("/__vendor__/pdf.min.js", "/__vendor__/pdf.worker.min.js"):
            return self._send_bytes(PDF_JS_SHIM.encode("utf-8"), "application/javascript; charset=utf-8")
        if req_path == "/__vendor__/fonts.css":
            return self._send_bytes(b"/* local font shim */\n", "text/css; charset=utf-8")
        if req_path == "/__vendor__/recaptcha.js":
            return self._send_bytes(RECAPTCHA_JS_SHIM.encode("utf-8"), "application/javascript; charset=utf-8")
        if req_path == "/api/v1/auth/captcha-config":
            return self._send_bytes(json.dumps({"ok": True, "provider": "recaptcha", "siteKey": os.environ.get("RECAPTCHA_SITE_KEY", "").strip()}).encode("utf-8"), "application/json; charset=utf-8", status=200)
        if req_path == "/api/v1/auth/session":
            repo = agy_service.get_state_repo()
            payload = repo.resolve_session(cf_email=self.headers.get("Cf-Access-Authenticated-User-Email"), account_header=self.headers.get("X-Lumen-Account"), session_header=self.headers.get("X-Lumen-Session"))
            return self._send_bytes(json.dumps(payload).encode("utf-8"), "application/json; charset=utf-8", status=200)
        if req_path == "/api/v1/state":
            repo = agy_service.get_state_repo()
            caller_ctx = repo.resolve_caller_context(cf_email=self.headers.get("Cf-Access-Authenticated-User-Email"), account_header=self.headers.get("X-Lumen-Account"), session_header=self.headers.get("X-Lumen-Session"))
            return self._send_bytes(json.dumps({"status": "ok", "state": repo.get_scoped_state(caller_ctx.account_id, caller_context=caller_ctx)}).encode("utf-8"), "application/json; charset=utf-8", status=200)
        if req_path == "/api/v1/attachments":
            repo = agy_service.get_state_repo()
            caller_ctx = repo.resolve_caller_context(cf_email=self.headers.get("Cf-Access-Authenticated-User-Email"), account_header=self.headers.get("X-Lumen-Account"), session_header=self.headers.get("X-Lumen-Session"))
            key = (parse_qs(parsed.query).get("key") or [""])[0]
            return self._send_bytes(json.dumps({"status": "ok", "key": key, "data": repo.get_attachment(key, account_id=caller_ctx.account_id, caller_context=caller_ctx)}).encode("utf-8"), "application/json; charset=utf-8", status=200)

        if req_path in ("/", "/index.html"):
            index_file = APP_SOURCE_DIR / "index.html"
            html = index_file.read_text(encoding="utf-8")
            html = html.replace(
                "https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Outfit:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap",
                "/__vendor__/fonts.css",
            )
            html = html.replace(
                "https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Outfit:wght@400;500;600;700&display=swap",
                "/__vendor__/fonts.css",
            )
            html = html.replace(
                "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js",
                "/__vendor__/pdf.min.js",
            )
            html = html.replace(
                "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.4.120/pdf.min.js",
                "/__vendor__/pdf.min.js",
            )
            html = html.replace(
                "https://cdn.jsdelivr.net/npm/chart.js",
                "/__vendor__/chart.js",
            )
            self._send_bytes(html.encode("utf-8"), "text/html; charset=utf-8")
            return

        if req_path in ("/welcome", "/welcome.html"):
            welcome_file = APP_SOURCE_DIR / "welcome.html"
            html = welcome_file.read_text(encoding="utf-8")
            html = html.replace(
                "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Outfit:wght@500;600;700;800&display=swap",
                "/__vendor__/fonts.css",
            )
            html = html.replace(
                "https://www.google.com/recaptcha/api.js?render=explicit",
                "/__vendor__/recaptcha.js",
            )
            self._send_bytes(html.encode("utf-8"), "text/html; charset=utf-8")
            return

        if req_path in ("/admin", "/admin.html"):
            admin_file = APP_SOURCE_DIR / "admin.html"
            html = admin_file.read_text(encoding="utf-8")
            html = html.replace(
                "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Outfit:wght@500;600;700;800&display=swap",
                "/__vendor__/fonts.css",
            )
            self._send_bytes(html.encode("utf-8"), "text/html; charset=utf-8")
            return

        rel_path = req_path.lstrip("/")
        resolved_root = APP_SOURCE_DIR.resolve()
        file_path: Path = (resolved_root / rel_path).resolve()
        if not file_path.is_relative_to(resolved_root) or not file_path.is_file():
            self._send_bytes(b"Not Found", "text/plain; charset=utf-8", status=404)
            return

        if file_path.suffix == ".js":
            js = file_path.read_text(encoding="utf-8")
            js = js.replace(
                "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js",
                "/__vendor__/pdf.worker.min.js",
            )
            self._send_bytes(js.encode("utf-8"), "application/javascript; charset=utf-8")
            return

        mime_type, _ = mimetypes.guess_type(str(file_path))
        self._send_bytes(file_path.read_bytes(), mime_type or "application/octet-stream")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        content_len = int(self.headers.get("Content-Length", "0"))
        body_bytes = self.rfile.read(content_len) if content_len > 0 else b""
        body_text = body_bytes.decode("utf-8", errors="ignore")
        if self._try_custom_api_handler(body_text):
            return

        if parsed.path == "/api/v1/auth/login":
            repo = agy_service.get_state_repo()
            req_obj = agy_service._parse_json_object(body_bytes)
            res = repo.verify_login(req_obj.get("email"), req_obj.get("password"))
            self._send_bytes(json.dumps(res).encode("utf-8"), "application/json; charset=utf-8", status=int(res.get("status_code") or 200))
            return
        if parsed.path in ("/api/v1/auth/password-reset/request", "/api/v1/auth/reset-request"):
            repo = agy_service.get_state_repo()
            req_obj = agy_service._parse_json_object(body_bytes)
            res = repo.request_password_reset(req_obj.get("email"))
            self._send_bytes(json.dumps(res).encode("utf-8"), "application/json; charset=utf-8", status=int(res.get("status_code") or 200))
            return
        if parsed.path in ("/api/v1/auth/password-reset/confirm", "/api/v1/auth/reset-confirm"):
            repo = agy_service.get_state_repo()
            req_obj = agy_service._parse_json_object(body_bytes)
            res = repo.confirm_password_reset(
                req_obj.get("email"),
                req_obj.get("code"),
                req_obj.get("newPassword"),
            )
            self._send_bytes(json.dumps(res).encode("utf-8"), "application/json; charset=utf-8", status=int(res.get("status_code") or 200))
            return
        if parsed.path == "/api/v1/auth/captcha/verify":
            repo = agy_service.get_state_repo()
            req_obj = agy_service._parse_json_object(body_bytes)
            res = agy_service._verify_recaptcha_token(
                req_obj.get("token"),
                secret=os.environ.get("RECAPTCHA_SECRET_KEY", "").strip(),
                session_secret=repo._session_secret,
                origin=self.headers.get("Origin"),
            )
            self._send_bytes(json.dumps(res).encode("utf-8"), "application/json; charset=utf-8", status=int(res.get("status_code") or 200))
            return
        if parsed.path in ("/api/v1/auth/trial-reminder", "/api/v1/auth/trial-renew", "/api/v1/auth/payment-method"):
            repo = agy_service.get_state_repo()
            caller_ctx = repo.resolve_caller_context(
                cf_email=self.headers.get("Cf-Access-Authenticated-User-Email"),
                account_header=self.headers.get("X-Lumen-Account"),
                session_header=self.headers.get("X-Lumen-Session"),
            )
            req_obj = agy_service._parse_json_object(body_bytes)
            if parsed.path == "/api/v1/auth/payment-method":
                res = repo.save_payment_method(
                    req_obj.get("email"),
                    caller_account=caller_ctx.account_id,
                    caller_context=caller_ctx,
                    card_holder_name=req_obj.get("cardHolderName", ""),
                    card_brand=req_obj.get("cardBrand", "Card"),
                    card_last4=req_obj.get("cardLast4", ""),
                    card_expiry=req_obj.get("cardExpiry", ""),
                    payment_method_token=req_obj.get("paymentMethodToken", ""),
                    pay_now=req_obj.get("payNow", False),
                )
            elif parsed.path == "/api/v1/auth/trial-reminder":
                res = repo.send_trial_renewal_reminder(req_obj.get("email"), caller_account=caller_ctx.account_id, caller_context=caller_ctx)
            else:
                res = repo.process_trial_renewal(req_obj.get("email"), caller_account=caller_ctx.account_id, caller_context=caller_ctx)
            self._send_bytes(json.dumps(res).encode("utf-8"), "application/json; charset=utf-8", status=403 if res.get("error") == "Forbidden." else int(res.get("status_code") or 200))
            return
        if parsed.path in ("/api/v1/state", "/api/v1/attachments"):
            repo = agy_service.get_state_repo()
            caller_ctx = repo.resolve_caller_context(
                cf_email=self.headers.get("Cf-Access-Authenticated-User-Email"),
                account_header=self.headers.get("X-Lumen-Account"),
                session_header=self.headers.get("X-Lumen-Session"),
            )
            try:
                if parsed.path == "/api/v1/state":
                    res = agy_service._handle_state_post(body_bytes, repo, caller_ctx, captcha_attestation=self.headers.get("X-Lumen-Captcha") or None)
                else:
                    res = agy_service._handle_attachments_post(body_bytes, repo, caller_ctx)
                self._send_bytes(json.dumps(res).encode("utf-8"), "application/json; charset=utf-8", status=200)
            except agy_service.PredictionServiceError as exc:
                err_env = agy_service.build_error_envelope(exc.error_code, exc.public_message)
                self._send_bytes(json.dumps(err_env).encode("utf-8"), "application/json; charset=utf-8", status=exc.status_code)
            return
        if parsed.path in ("/api/v1/einvoice/submit", "/api/v1/einvoice/webhook", "/api/v1/einvoice/inbound"):
            repo = agy_service.get_state_repo()
            caller_ctx = repo.resolve_caller_context(
                cf_email=self.headers.get("Cf-Access-Authenticated-User-Email"),
                account_header=self.headers.get("X-Lumen-Account"),
                session_header=self.headers.get("X-Lumen-Session"),
            )
            if not parsed.path.endswith("webhook") and caller_ctx.role in ("viewer", "unauthenticated"):
                err_env = agy_service.build_error_envelope("forbidden", "Read-only viewer role cannot submit or import e-invoices.")
                self._send_bytes(json.dumps(err_env).encode("utf-8"), "application/json; charset=utf-8", status=403)
                return
            payload = agy_service._parse_json_object(body_bytes)
            try:
                res = repo.handle_einvoice_webhook(payload) if parsed.path.endswith("webhook") else (repo.receive_inbound_einvoice(payload, caller_account=caller_ctx.account_id, caller_context=caller_ctx) if parsed.path.endswith("inbound") else repo.submit_einvoice(payload, caller_account=caller_ctx.account_id, caller_context=caller_ctx))
                self._send_bytes(json.dumps(res).encode("utf-8"), "application/json; charset=utf-8", status=int(res.get("status_code") or 200))
            except PermissionError as exc:
                self._send_bytes(json.dumps(agy_service.build_error_envelope("forbidden", str(exc))).encode("utf-8"), "application/json; charset=utf-8", status=403)
            return
        if parsed.path.startswith("/api/v1/prediction/"):
            if "dogs_only" in body_text or "non_invoice_dog" in body_text:
                err_obj = {
                    "error": {"code": "invalid_invoice_document", "message": "The uploaded PDF only contains photos of dogs and is not a valid invoice."},
                    "text": json.dumps({"isValidInvoice": False, "documentType": "non_invoice", "rejectionReason": "The uploaded PDF only contains photos of dogs."}),
                }
                self._send_bytes(json.dumps(err_obj).encode("utf-8"), "application/json; charset=utf-8", status=422)
                return
            response_obj = build_mock_ai_response(body_text)
            self._send_bytes(
                json.dumps(response_obj).encode("utf-8"),
                "application/json; charset=utf-8",
                status=200,
            )
            return

        err_env = agy_service.build_error_envelope("not_found", "Endpoint not found.")
        self._send_bytes(json.dumps(err_env).encode("utf-8"), "application/json; charset=utf-8", status=404)


def is_port_listening(host: str, port: int) -> bool:
    """Return True if a TCP server is already accepting connections on host:port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def start_background_server(host: str = HOST, port: int = PORT) -> ThreadingHTTPServer | None:
    """Start the local HTTP server in a daemon thread if not already listening."""
    if is_port_listening(host, port):
        return None
    server = ThreadingHTTPServer((host, port), BookkeepingRequestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


if __name__ == "__main__":
    srv = ThreadingHTTPServer((HOST, PORT), BookkeepingRequestHandler)
    print(f"Serving Lumen Accounting Suite from {APP_SOURCE_DIR} on http://{HOST}:{PORT}")
    srv.serve_forever()
