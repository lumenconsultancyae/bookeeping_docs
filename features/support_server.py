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
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from features.config import APP_SOURCE_DIR, HOST, PORT

CHART_JS_SHIM = """
(function(window) {
    class Chart {
        constructor(ctx, config) {
            this.ctx = ctx;
            this.config = config || {};
            this._renderCanvasPreview();
        }
        _renderCanvasPreview() {
            try {
                const canvas = this.ctx && this.ctx.canvas ? this.ctx.canvas : this.ctx;
                if (!canvas || !canvas.getContext) return;
                const c = canvas.getContext('2d');
                const w = canvas.width || 600;
                const h = canvas.height || 260;
                c.clearRect(0, 0, w, h);
                c.fillStyle = '#f8fafc';
                c.fillRect(0, 0, w, h);
                const labels = (this.config.data && this.config.data.labels) || [];
                const datasets = (this.config.data && this.config.data.datasets) || [];
                const barWidth = Math.max(16, Math.floor((w - 80) / Math.max(labels.length * 3, 1)));
                labels.forEach((label, idx) => {
                    const xBase = 50 + idx * (barWidth * 2.5);
                    datasets.forEach((ds, dIdx) => {
                        const val = Number((ds.data && ds.data[idx]) || 0);
                        const barH = val > 0 ? Math.min(h - 60, Math.max(12, Math.log10(val + 10) * 35)) : 4;
                        c.fillStyle = ds.backgroundColor || (dIdx === 0 ? '#10b981' : '#f43f5e');
                        c.fillRect(xBase + dIdx * (barWidth + 4), h - 35 - barH, barWidth, barH);
                    });
                    c.fillStyle = '#475569';
                    c.font = '12px sans-serif';
                    c.fillText(String(label), xBase, h - 15);
                });
            } catch (e) {}
        }
        destroy() {}
        update() { this._renderCanvasPreview(); }
    }
    window.Chart = Chart;
})(window);
"""

PDF_JS_SHIM = """
(function(window) {
    const pdfjsLib = {
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
            "entityName": "Al Noor Trading LLC",
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
    if "MFZ-339673" in body_text or "application/pdf" in body_text:
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

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        return  # Silence per-request stdout noise during BDD test runs

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

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        req_path = parsed.path

        if req_path == "/__vendor__/chart.js":
            self._send_bytes(CHART_JS_SHIM.encode("utf-8"), "application/javascript; charset=utf-8")
            return
        if req_path in ("/__vendor__/pdf.min.js", "/__vendor__/pdf.worker.min.js"):
            self._send_bytes(PDF_JS_SHIM.encode("utf-8"), "application/javascript; charset=utf-8")
            return
        if req_path == "/__vendor__/fonts.css":
            self._send_bytes(b"/* local font shim */\n", "text/css; charset=utf-8")
            return

        if req_path in ("/", "/index.html"):
            index_file = APP_SOURCE_DIR / "index.html"
            html = index_file.read_text(encoding="utf-8")
            html = html.replace(
                "https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Outfit:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap",
                "/__vendor__/fonts.css",
            )
            html = html.replace(
                "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js",
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

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        content_len = int(self.headers.get("Content-Length", "0"))
        body_bytes = self.rfile.read(content_len) if content_len > 0 else b""
        body_text = body_bytes.decode("utf-8", errors="ignore")

        if parsed.path.startswith("/api/"):
            response_obj = build_mock_ai_response(body_text)
            self._send_bytes(
                json.dumps(response_obj).encode("utf-8"),
                "application/json; charset=utf-8",
                status=200,
            )
            return

        self._send_bytes(b'{"status":"ok"}', "application/json; charset=utf-8", status=200)


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
