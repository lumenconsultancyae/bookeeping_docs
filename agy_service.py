#!/usr/bin/env python3
"""HTTP prediction service wrapping the `agy` CLI the same way Argiei worker instances execute it.

Replaces the external Flowise AI container on port 3000 while preserving the
`/api/v1/prediction/*` request/response contract expected by `script.js`.
"""

from __future__ import annotations

import base64
import binascii
from collections.abc import Mapping
from email.parser import BytesParser
from email.policy import default as default_email_policy
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
from urllib.parse import urlparse
import uuid

HOST = os.environ.get("AGY_HOST", "0.0.0.0")
PORT = int(os.environ.get("AGY_PORT", "3000"))
AGY_MODEL = os.environ.get("AGY_MODEL", "Gemini 4 Argon (High)")
AGY_TIMEOUT = os.environ.get("AGY_TIMEOUT", "99999h")
SUBPROCESS_TIMEOUT_SECONDS = int(os.environ.get("AGY_SUBPROCESS_TIMEOUT", "240"))
MAX_REQUEST_BYTES = int(os.environ.get("AGY_MAX_REQUEST_BYTES", str(50 * 1024 * 1024)))
AGY_API_SECRET = os.environ.get("AGY_API_SECRET", "").strip()
REQUIRED_CLIENT_HEADER_VALUE = os.environ.get("AGY_CLIENT_HEADER_VALUE", "lumen-bookkeeping-web").strip()
REQUIRE_ORIGIN = os.environ.get("AGY_REQUIRE_ORIGIN", "false").strip().lower() in ("1", "true", "yes")
DEFAULT_ALLOWED_ORIGINS = (
    "https://bookeeping.lumenconsultancy.net",
    "https://bookkeeping.lumenconsultancy.net",
    "https://lumen-bookkeeping.pages.dev",
    "http://localhost:9091",
    "http://127.0.0.1:9091",
    "http://bookkeeping-web",
    "http://bookkeeping-web:80",
)
ALLOWED_ORIGINS = tuple(
    origin.strip().rstrip("/")
    for origin in os.environ.get("AGY_ALLOWED_ORIGINS", ",".join(DEFAULT_ALLOWED_ORIGINS)).split(",")
    if origin.strip()
)

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
                                        ctx.fillText('PDF Document Page ' + pageNum, 40, 60);
                                    }
                                } catch (e) {}
                                return { promise: Promise.resolve() };
                            },
                            getTextContent: function() {
                                return Promise.resolve({
                                    items: []
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


class PredictionServiceError(Exception):
    """Base structured exception for prediction HTTP error translation."""

    status_code: int = 500
    error_code: str = "internal_error"
    public_message: str = "An unexpected error occurred while processing the prediction request."

    def __init__(self, public_message: str | None = None, *, internal_detail: str | None = None) -> None:
        super().__init__(internal_detail or public_message or self.public_message)
        if public_message:
            self.public_message = public_message
        self.internal_detail = internal_detail or self.public_message


class InvalidPredictionRequestError(PredictionServiceError):
    """Raised when the client submits malformed JSON, invalid types, or corrupt Base64."""

    status_code = 400
    error_code = "invalid_request"
    public_message = "Invalid prediction request payload."


class UnauthorizedPredictionRequestError(PredictionServiceError):
    """Raised when a request lacks the required application client header or proxy shared secret."""

    status_code = 401
    error_code = "unauthorized"
    public_message = "Unauthorized: prediction endpoint is restricted to the Lumen Bookkeeping application."


class ForbiddenOriginPredictionError(PredictionServiceError):
    """Raised when a request originates from an untrusted external domain."""

    status_code = 403
    error_code = "forbidden_origin"
    public_message = "Forbidden: request origin is not authorized to access this service."


class PayloadTooLargeError(PredictionServiceError):
    """Raised when Content-Length exceeds MAX_REQUEST_BYTES."""

    status_code = 413
    error_code = "payload_too_large"
    public_message = "Request payload exceeds the maximum allowed size."


class PredictionTimeoutError(PredictionServiceError):
    """Raised when the `agy` CLI subprocess exceeds SUBPROCESS_TIMEOUT_SECONDS."""

    status_code = 504
    error_code = "prediction_timeout"
    public_message = "AI prediction timed out."


class UpstreamPredictionError(PredictionServiceError):
    """Raised when the `agy` CLI subprocess exits with a non-zero code."""

    status_code = 502
    error_code = "upstream_prediction_error"
    public_message = "AI prediction engine failed to process the request."


def build_error_envelope(error_code: str, message: str) -> dict:
    """Return a consistent JSON error envelope that preserves the `text` fallback for `script.js`."""
    return {
        "error": {
            "code": error_code,
            "message": message,
        },
        "text": "```json\n{}\n```",
    }


def _sanitize_filename(name: str, index: int, mime: str) -> str:
    """Return a collision-safe, traversal-proof filename prefixed with the upload index."""
    base_raw = os.path.basename(name or "")
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", base_raw).lstrip(".-_")
    mime_lower = (mime or "").lower()
    if not cleaned or cleaned in (".", ".."):
        if "pdf" in mime_lower:
            ext = ".pdf"
        elif "jpeg" in mime_lower or "jpg" in mime_lower:
            ext = ".jpg"
        else:
            ext = ".png"
        cleaned = f"document_{index}{ext}"
    elif "pdf" in mime_lower and not cleaned.lower().endswith(".pdf"):
        cleaned = f"{cleaned}.pdf"
    return f"{index}_{cleaned}"


def _parse_multipart_form_data(content_type: str, body: bytes) -> tuple[str, list[dict]]:
    """Extract `question` and any file uploads from a `multipart/form-data` request body."""
    raw_headers = f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8")
    msg = BytesParser(policy=default_email_policy).parsebytes(raw_headers + body)
    question = ""
    uploads: list[dict] = []

    if not msg.is_multipart():
        raise InvalidPredictionRequestError("Malformed multipart/form-data payload.")

    for part in msg.iter_parts():
        disposition = part.get_content_disposition()
        if disposition != "form-data":
            continue
        field_name = part.get_param("name", header="content-disposition")
        filename = part.get_filename()
        payload_bytes = part.get_payload(decode=True) or b""
        if filename:
            mime = part.get_content_type() or "application/octet-stream"
            b64_str = base64.b64encode(payload_bytes).decode("ascii")
            uploads.append(
                {
                    "name": filename,
                    "mime": mime,
                    "data": f"data:{mime};base64,{b64_str}",
                }
            )
        elif field_name == "question":
            question = payload_bytes.decode("utf-8", errors="replace")

    return question, uploads


def _parse_json_prediction_request(body: bytes) -> tuple[str, list[dict]]:
    """Validate and extract `question` and `uploads` from a JSON request body."""
    try:
        decoded = body.decode("utf-8") if body else "{}"
        payload = json.loads(decoded or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidPredictionRequestError(
            "Request body must be valid UTF-8 JSON.",
            internal_detail=str(exc),
        ) from exc

    if not isinstance(payload, dict):
        raise InvalidPredictionRequestError("JSON request payload must be an object.")

    raw_question = payload.get("question", "")
    if raw_question is None:
        raw_question = ""
    if not isinstance(raw_question, str):
        raise InvalidPredictionRequestError("Field 'question' must be a string.")

    raw_uploads = payload.get("uploads", [])
    if raw_uploads is None:
        raw_uploads = []
    if not isinstance(raw_uploads, list) or any(not isinstance(u, dict) for u in raw_uploads):
        raise InvalidPredictionRequestError("Field 'uploads' must be a list of objects.")

    return raw_question, raw_uploads


def _write_uploads_to_dir(uploads: list[dict], target_dir: Path) -> list[Path]:
    """Decode base64 data URLs from `uploads` into `target_dir` and return their resolved paths."""
    resolved_target_dir = target_dir.resolve()
    saved_paths: list[Path] = []
    for idx, item in enumerate(uploads):
        if not isinstance(item, dict):
            raise InvalidPredictionRequestError("Each upload entry must be an object.")
        data_val = item.get("data", "")
        if not isinstance(data_val, str):
            raise InvalidPredictionRequestError("Upload 'data' field must be a base64 string.")
        if not data_val:
            continue

        mime = str(item.get("mime") or "image/jpeg")
        raw_name = item.get("name")
        name_str = raw_name if isinstance(raw_name, str) else ""
        safe_name = _sanitize_filename(name_str, idx, mime)

        if "," in data_val and data_val.startswith("data:"):
            _, b64_payload = data_val.split(",", 1)
        else:
            b64_payload = data_val

        try:
            file_bytes = base64.b64decode(b64_payload, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise InvalidPredictionRequestError(
                f"Invalid base64 encoding in upload at index {idx}.",
                internal_detail=str(exc),
            ) from exc

        file_path = (resolved_target_dir / safe_name).resolve()
        if not file_path.is_relative_to(resolved_target_dir) or file_path == resolved_target_dir:
            raise InvalidPredictionRequestError("Invalid upload filename.")

        file_path.write_bytes(file_bytes)
        saved_paths.append(file_path)

    return saved_paths


def run_agy_prediction(question: str, uploads: list[dict]) -> dict:
    """Execute `agy` non-interactively using the same CLI flags as Argiei worker instances."""
    base_tmp = Path(tempfile.gettempdir()) / "agy_requests"
    base_tmp.mkdir(parents=True, exist_ok=True)
    req_dir = (base_tmp / f"req_{uuid.uuid4().hex[:12]}").resolve()
    req_dir.mkdir(parents=True, exist_ok=True)

    try:
        saved_files = _write_uploads_to_dir(uploads, req_dir)
        if saved_files:
            files_list = "\n".join(f"- {p}" for p in saved_files)
            full_prompt = (
                "You are an accounting document extraction engine.\n"
                f"First, call the `read_file` tool ONCE on each uploaded document file below:\n{files_list}\n\n"
                "CRITICAL RULES:\n"
                "- Use ONLY the `read_file` tool. Do NOT call `run_command`, `write_file`, `edit_file`, or any other tool.\n"
                "- Extract all values directly from the document content returned by `read_file`.\n"
                "- Ensure every line item `amount` and `unitPrice` is the pre-tax net amount (excluding VAT/tax), "
                "and `subtotal` is the sum of pre-tax line item amounts so that `subtotal - discount + tax = total`.\n"
                "- Respond ONLY with the requested ```json ... ``` code block (no extra prose):\n\n"
                f"{question}"
            )
        else:
            full_prompt = (
                "You are an accounting document extraction engine.\n"
                "CRITICAL RULES:\n"
                "- Do NOT call `run_command`, `write_file`, `edit_file`, or any other tool.\n"
                "- Fulfill the extraction instructions below and respond ONLY with the requested "
                "```json ... ``` code block (no extra prose):\n\n"
                f"{question}"
            )

        cmd = [
            "agy",
            "--mode",
            "accept-edits",
            "--dangerously-skip-permissions",
            "--disable-slash-commands",
            "--output-format",
            "json",
            "--model",
            AGY_MODEL,
            "--print-timeout",
            AGY_TIMEOUT,
            "--add-dir",
            str(req_dir),
            "--print",
            full_prompt,
        ]

        try:
            proc = subprocess.run(
                cmd,
                cwd=str(req_dir),
                capture_output=True,
                text=True,
                timeout=SUBPROCESS_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise PredictionTimeoutError(
                "AI prediction timed out.",
                internal_detail=f"agy subprocess timed out after {SUBPROCESS_TIMEOUT_SECONDS}s",
            ) from exc

        stdout = (proc.stdout or "").strip()
        stderr = (proc.stderr or "").strip()

        parsed_json: dict | None = None
        for line in reversed(stdout.splitlines()):
            line = line.strip()
            if line.startswith("{") and line.endswith("}"):
                try:
                    candidate = json.loads(line)
                    if isinstance(candidate, dict):
                        parsed_json = candidate
                        break
                except json.JSONDecodeError:
                    continue

        if parsed_json is not None:
            response_text = str(parsed_json.get("response") or "")
            conv_id = str(parsed_json.get("conversation_id") or "")
            status = str(parsed_json.get("status") or "SUCCESS")
            print(f"[agy] Completed conversation_id={conv_id} status={status}", flush=True)
            return {
                "text": response_text,
                "conversation_id": conv_id,
                "status": status,
            }

        if proc.returncode != 0:
            raise UpstreamPredictionError(
                "AI prediction engine failed to process the request.",
                internal_detail=f"agy exited with code {proc.returncode}: {stderr or stdout}",
            )

        return {
            "text": stdout,
            "status": "SUCCESS",
        }
    finally:
        shutil.rmtree(req_dir, ignore_errors=True)


def _validate_content_length(header_val: str | None) -> int:
    """Validate and return the integer Content-Length within MAX_REQUEST_BYTES."""
    if header_val is None or header_val == "":
        return 0
    try:
        length = int(header_val)
    except ValueError as exc:
        raise InvalidPredictionRequestError("Invalid Content-Length header.") from exc
    if length < 0:
        raise InvalidPredictionRequestError("Content-Length cannot be negative.")
    if length > MAX_REQUEST_BYTES:
        raise PayloadTooLargeError()
    return length


def _get_header_case_insensitive(headers: Mapping[str, str], name: str) -> str:
    """Read a header value case-insensitively from an HTTPMessage or dict."""
    direct = headers.get(name)
    if direct is not None:
        return str(direct).strip()
    target_lower = name.lower()
    for key, val in headers.items():
        if key.lower() == target_lower and val is not None:
            return str(val).strip()
    return ""


def _extract_origin_from_url(url_or_origin: str) -> str:
    """Normalize an Origin or Referer URL into `scheme://netloc`."""
    cleaned = (url_or_origin or "").strip().rstrip("/")
    if not cleaned:
        return ""
    parsed = urlparse(cleaned)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


def _is_allowed_origin(origin: str | None) -> bool:
    """Return True only if `origin` matches our trusted Lumen Bookkeeping application origins."""
    normalized = _extract_origin_from_url(origin or "")
    if not normalized:
        return False
    allowed_lower = {item.lower() for item in ALLOWED_ORIGINS}
    if normalized in allowed_lower:
        return True
    if re.match(r"^https://[a-z0-9-]+\.lumen-bookkeeping\.pages\.dev$", normalized):
        return True
    if re.match(r"^http://(localhost|127\.0\.0\.1|bookkeeping-web)(:\d+)?$", normalized):
        return True
    return False


def _verify_prediction_request_security(headers: Mapping[str, str]) -> str | None:
    """Enforce multi-layer application security on `/api/v1/prediction/*` requests.

    1. When `AGY_API_SECRET` is configured, verifies `X-Agy-Proxy-Secret` in constant time.
    2. Verifies the `X-Lumen-Client: lumen-bookkeeping-web` application handshake header.
    3. Verifies `Origin` (or `Referer`) against the trusted application origin allowlist.
    """
    if AGY_API_SECRET:
        provided_secret = _get_header_case_insensitive(headers, "X-Agy-Proxy-Secret")
        if not provided_secret or not hmac.compare_digest(
            provided_secret.encode("utf-8"),
            AGY_API_SECRET.encode("utf-8"),
        ):
            raise UnauthorizedPredictionRequestError(
                "Unauthorized: valid proxy authentication secret is required.",
                internal_detail="Missing or invalid X-Agy-Proxy-Secret header",
            )

    client_header = _get_header_case_insensitive(headers, "X-Lumen-Client")
    if client_header != REQUIRED_CLIENT_HEADER_VALUE:
        raise UnauthorizedPredictionRequestError(
            "Unauthorized: prediction endpoint is restricted to the Lumen Bookkeeping application.",
            internal_detail=f"Missing or invalid X-Lumen-Client header: {client_header!r}",
        )

    raw_origin = _get_header_case_insensitive(headers, "Origin")
    raw_referer = _get_header_case_insensitive(headers, "Referer")
    candidate_origin = _extract_origin_from_url(raw_origin) if raw_origin else _extract_origin_from_url(raw_referer)

    if raw_origin or raw_referer:
        if not candidate_origin or not _is_allowed_origin(candidate_origin):
            raise ForbiddenOriginPredictionError(
                "Forbidden: request origin is not authorized to access this service.",
                internal_detail=f"Rejected untrusted origin={raw_origin!r} referer={raw_referer!r}",
            )
        return candidate_origin

    if REQUIRE_ORIGIN:
        raise ForbiddenOriginPredictionError(
            "Forbidden: request origin header is required.",
            internal_detail="Missing both Origin and Referer headers while AGY_REQUIRE_ORIGIN is enabled",
        )

    return None


class AgyPredictionHandler(BaseHTTPRequestHandler):
    """HTTP request handler exposing Flowise-compatible `/api/v1/prediction/*` endpoints."""

    def _send_json(self, payload: dict, status: int = 200) -> None:
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        req_origin = _extract_origin_from_url(self.headers.get("Origin", ""))
        if req_origin and _is_allowed_origin(req_origin):
            self.send_header("Access-Control-Allow-Origin", req_origin)
            self.send_header("Vary", "Origin")
        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type, Authorization, X-Lumen-Client, X-Agy-Proxy-Secret",
        )
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(raw)

    def do_OPTIONS(self) -> None:  # noqa: N802
        raw_origin = self.headers.get("Origin", "")
        if raw_origin and not _is_allowed_origin(raw_origin):
            self._send_json(
                build_error_envelope(
                    "forbidden_origin",
                    "Forbidden: request origin is not authorized to access this service.",
                ),
                status=403,
            )
            return
        self._send_json({"status": "ok"}, status=200)

    def _send_bytes(self, raw: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/__vendor__/chart.js":
            self._send_bytes(CHART_JS_SHIM.encode("utf-8"), "application/javascript; charset=utf-8")
            return
        if parsed.path in ("/__vendor__/pdf.min.js", "/__vendor__/pdf.worker.min.js"):
            self._send_bytes(PDF_JS_SHIM.encode("utf-8"), "application/javascript; charset=utf-8")
            return
        if parsed.path == "/__vendor__/fonts.css":
            self._send_bytes(b"/* local font shim */\n", "text/css; charset=utf-8")
            return
        if parsed.path in ("/", "/health", "/api/v1/ping"):
            self._send_json(
                {
                    "status": "ok",
                    "engine": "agy",
                    "model": AGY_MODEL,
                },
                status=200,
            )
            return
        self._send_json(build_error_envelope("not_found", "Endpoint not found."), status=404)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/api/"):
            self._send_json(build_error_envelope("not_found", "Endpoint not found."), status=404)
            return

        try:
            _verify_prediction_request_security(self.headers)
            content_len = _validate_content_length(self.headers.get("Content-Length"))
            body = self.rfile.read(content_len) if content_len > 0 else b""
            content_type = self.headers.get("Content-Type", "")

            if "multipart/form-data" in content_type:
                question, uploads = _parse_multipart_form_data(content_type, body)
            else:
                question, uploads = _parse_json_prediction_request(body)

            result = run_agy_prediction(question=question, uploads=uploads)
            self._send_json(result, status=200)
        except PredictionServiceError as exc:
            print(f"[agy-error] {exc.error_code}: {exc.internal_detail}", file=sys.stderr, flush=True)
            self._send_json(
                build_error_envelope(exc.error_code, exc.public_message),
                status=exc.status_code,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[agy-error] unexpected: {exc!r}", file=sys.stderr, flush=True)
            self._send_json(
                build_error_envelope(
                    "internal_error",
                    "An unexpected error occurred while processing the prediction request.",
                ),
                status=500,
            )


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), AgyPredictionHandler)

    def _handle_shutdown(signum: int, _frame) -> None:
        print(f"Received signal {signum}, shutting down agy prediction service...", flush=True)
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, _handle_shutdown)
    signal.signal(signal.SIGINT, _handle_shutdown)

    print(f"Starting agy prediction service on http://{HOST}:{PORT} (model={AGY_MODEL})", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
