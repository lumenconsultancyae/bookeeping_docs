"""HTTP prediction service wrapping the `agy` CLI the same way Argiei worker instances execute it."""

from __future__ import annotations

import base64
import binascii
import hmac
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import uuid
from collections.abc import Mapping
from email.parser import BytesParser
from email.policy import default as default_email_policy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from invoice_validation import (
    build_extraction_prompt as _build_extraction_prompt,
)
from invoice_validation import (
    validate_ai_document_response as _run_validate_ai_document_response,
)
from invoice_validation import (
    validate_uploaded_file_bytes as _run_validate_uploaded_file_bytes,
)
from state_repository import (
    ADMIN_EMAIL,  # noqa: F401
    DEFAULT_ADMIN_HASH,  # noqa: F401
    DEFAULT_ADMIN_SALT,  # noqa: F401
    LOCAL_ONLY_KEYS,  # noqa: F401
    CallerContext,
    LumenStateRepository,
    resolve_default_state_db_path,
)
from state_repository import (
    compute_password_hash as _compute_password_hash,  # noqa: F401
)
from state_repository import (
    is_excluded_state_key as _is_excluded_state_key,  # noqa: F401
)
from state_repository import (
    safe_json as _safe_json,  # noqa: F401
)
from state_repository import (
    strip_account_secrets as _strip_account_secrets,  # noqa: F401
)
from state_repository import (
    verify_password_hash as _verify_password_hash,  # noqa: F401
)
from state_repository import (
    verify_recaptcha_token as _verify_recaptcha_token,
)
from vendor_shims import CHART_JS_SHIM, PDF_JS_SHIM

HOST = os.environ.get("AGY_HOST", "0.0.0.0")
PORT = int(os.environ.get("AGY_PORT", "3000"))
AGY_MODEL = os.environ.get("AGY_MODEL", "Gemini 4 Argon (High)")
AGY_TIMEOUT = os.environ.get("AGY_TIMEOUT", "99999h")
SUBPROCESS_TIMEOUT_SECONDS = int(os.environ.get("AGY_SUBPROCESS_TIMEOUT", "240"))
_AGY_SEMAPHORE = threading.BoundedSemaphore(int(os.environ.get("AGY_MAX_CONCURRENT", "2")))
MAX_REQUEST_BYTES = int(os.environ.get("AGY_MAX_REQUEST_BYTES", str(50 * 1024 * 1024)))
AGY_API_SECRET = os.environ.get("AGY_API_SECRET", "").strip()
REQUIRED_CLIENT_HEADER_VALUE = os.environ.get("AGY_CLIENT_HEADER_VALUE", "lumen-bookkeeping-web").strip()
REQUIRE_ORIGIN = os.environ.get("AGY_REQUIRE_ORIGIN", "false").strip().lower() in ("1", "true", "yes")
DEFAULT_ALLOWED_ORIGINS = (
    "https://bookeeping.lumenconsultancy.net", "https://bookkeeping.lumenconsultancy.net",
    "https://lumen-bookkeeping.pages.dev", "http://localhost:9091", "http://127.0.0.1:9091",
    "http://localhost:8199", "http://127.0.0.1:8199", "http://localhost:8088", "http://127.0.0.1:8088",
    "http://localhost:8086", "http://127.0.0.1:8086", "http://bookkeeping-web", "http://bookkeeping-web:80",
)
ALLOWED_ORIGINS = tuple(
    origin.strip().rstrip("/")
    for origin in os.environ.get("AGY_ALLOWED_ORIGINS", ",".join(DEFAULT_ALLOWED_ORIGINS)).split(",")
    if origin.strip()
)


class PredictionServiceError(Exception):
    """Base structured error raised by the prediction and persistence service."""

    status_code = 500
    error_code = "internal_error"
    public_message = "An unexpected error occurred while processing the prediction request."

    def __init__(self, public_message: str | None = None, *, internal_detail: str | None = None) -> None:
        super().__init__(internal_detail or public_message or self.public_message)
        if public_message:
            self.public_message = public_message
        self.internal_detail = internal_detail or self.public_message


class InvalidPredictionRequestError(PredictionServiceError):
    status_code = 400
    error_code = "invalid_request"
    public_message = "Invalid prediction request payload."


class UnauthorizedPredictionRequestError(PredictionServiceError):
    status_code = 401
    error_code = "unauthorized"
    public_message = "Unauthorized: prediction endpoint is restricted to the Lumen Bookkeeping application."


class ForbiddenOriginPredictionError(PredictionServiceError):
    status_code = 403
    error_code = "forbidden_origin"
    public_message = "Forbidden: request origin is not authorized to access this service."


class ForbiddenRoleError(PredictionServiceError):
    status_code = 403
    error_code = "forbidden"
    public_message = "Forbidden: your role or profile permissions do not allow this action."


class PayloadTooLargeError(PredictionServiceError):
    status_code = 413
    error_code = "payload_too_large"
    public_message = "Request payload exceeds the maximum allowed size."


class PredictionTimeoutError(PredictionServiceError):
    status_code = 504
    error_code = "prediction_timeout"
    public_message = "AI prediction timed out."


class UpstreamPredictionError(PredictionServiceError):
    status_code = 502
    error_code = "upstream_prediction_error"
    public_message = "AI prediction engine failed to process the request."


class InvalidInvoiceDocumentError(PredictionServiceError):
    status_code = 422
    error_code = "invalid_invoice_document"
    public_message = "The uploaded document is not a valid invoice, bill, or receipt."


def build_error_envelope(error_code: str, message: str) -> dict:
    """Return a Flowise-compatible JSON error envelope."""
    return {"error": {"code": error_code, "message": message}, "text": "```json\n{}\n```"}


def _sanitize_filename(name: str, index: int, mime: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", os.path.basename(name or "")).lstrip(".-_")
    mime_lower = (mime or "").lower()
    if not cleaned or cleaned in (".", ".."):
        ext = ".pdf" if "pdf" in mime_lower else (".jpg" if ("jpeg" in mime_lower or "jpg" in mime_lower) else ".png")
        cleaned = f"document_{index}{ext}"
    elif "pdf" in mime_lower and not cleaned.lower().endswith(".pdf"):
        cleaned = f"{cleaned}.pdf"
    return f"{index}_{cleaned}"


def _parse_multipart_form_data(content_type: str, body: bytes) -> tuple[str, list[dict]]:
    raw_headers = f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode()
    msg = BytesParser(policy=default_email_policy).parsebytes(raw_headers + body)
    if not msg.is_multipart():
        raise InvalidPredictionRequestError("Malformed multipart/form-data payload.")
    question, uploads = "", []
    for part in msg.iter_parts():
        if part.get_content_disposition() != "form-data":
            continue
        field_name, filename = part.get_param("name", header="content-disposition"), part.get_filename()
        payload_bytes = part.get_payload(decode=True) or b""
        if filename:
            mime = part.get_content_type() or "application/octet-stream"
            b64_str = base64.b64encode(payload_bytes).decode("ascii")
            uploads.append({"name": filename, "mime": mime, "data": f"data:{mime};base64,{b64_str}"})
        elif field_name == "question":
            question = payload_bytes.decode("utf-8", errors="replace")
    return question, uploads


def _parse_json_prediction_request(body: bytes) -> tuple[str, list[dict]]:
    payload = _parse_json_object(body)
    raw_question = "" if payload.get("question") is None else payload.get("question", "")
    if not isinstance(raw_question, str):
        raise InvalidPredictionRequestError("Field 'question' must be a string.")
    raw_uploads = [] if payload.get("uploads") is None else payload.get("uploads", [])
    if not isinstance(raw_uploads, list) or any(not isinstance(u, dict) for u in raw_uploads):
        raise InvalidPredictionRequestError("Field 'uploads' must be a list of objects.")
    return raw_question, raw_uploads


def _validate_uploaded_file_bytes(file_bytes: bytes, safe_name: str, mime: str) -> None:
    _run_validate_uploaded_file_bytes(file_bytes, safe_name, mime, InvalidInvoiceDocumentError)


def _validate_ai_document_response(question: str, response_text: str, *, has_uploads: bool) -> None:
    _run_validate_ai_document_response(question, response_text, has_uploads=has_uploads, error_cls=InvalidInvoiceDocumentError)


def _write_uploads_to_dir(uploads: list[dict], target_dir: Path) -> list[Path]:
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
        raw_name, mime_val = item.get("name"), str(item.get("mime") or "image/jpeg")
        safe_name = _sanitize_filename(raw_name if isinstance(raw_name, str) else "", idx, mime_val)
        b64_payload = data_val.split(",", 1)[1] if ("," in data_val and data_val.startswith("data:")) else data_val
        try:
            file_bytes = base64.b64decode(b64_payload, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise InvalidPredictionRequestError(f"Invalid base64 encoding in upload at index {idx}.", internal_detail=str(exc)) from exc
        _validate_uploaded_file_bytes(file_bytes, safe_name, mime_val)
        file_path = (resolved_target_dir / safe_name).resolve()
        if not file_path.is_relative_to(resolved_target_dir) or file_path == resolved_target_dir:
            raise InvalidPredictionRequestError("Invalid upload filename.")
        file_path.write_bytes(file_bytes)
        saved_paths.append(file_path)
    return saved_paths


def run_agy_prediction(question: str, uploads: list[dict]) -> dict:
    """Execute `agy` non-interactively using the same CLI flags as Argiei worker instances."""
    req_dir = (Path(tempfile.gettempdir()) / "agy_requests" / f"req_{uuid.uuid4().hex[:12]}").resolve()
    req_dir.mkdir(parents=True, exist_ok=True)
    try:
        saved_files = _write_uploads_to_dir(uploads, req_dir)
        full_prompt = _build_extraction_prompt(question, saved_files)
        cmd = [
            "agy", "--mode", "accept-edits", "--dangerously-skip-permissions",
            "--disable-slash-commands", "--output-format", "json", "--model", AGY_MODEL,
            "--print-timeout", AGY_TIMEOUT, "--add-dir", str(req_dir), "--print", full_prompt,
        ]
        try:
            with _AGY_SEMAPHORE:
                proc = subprocess.run(cmd, cwd=str(req_dir), capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT_SECONDS, check=False)
        except subprocess.TimeoutExpired as exc:
            raise PredictionTimeoutError("AI prediction timed out.", internal_detail=f"agy subprocess timed out after {SUBPROCESS_TIMEOUT_SECONDS}s") from exc

        stdout, stderr = (proc.stdout or "").strip(), (proc.stderr or "").strip()
        parsed_json = None
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
            conv_id, status = str(parsed_json.get("conversation_id") or ""), str(parsed_json.get("status") or "SUCCESS")
            response_text = str(parsed_json.get("response") or "")
            _validate_ai_document_response(question, response_text, has_uploads=bool(saved_files))
            print(f"[agy] Completed conversation_id={conv_id} status={status}", flush=True)
            return {"text": response_text, "conversation_id": conv_id, "status": status}
        if proc.returncode != 0:
            raise UpstreamPredictionError("AI prediction engine failed to process the request.", internal_detail=f"agy exited with code {proc.returncode}: {stderr or stdout}")
        _validate_ai_document_response(question, stdout, has_uploads=bool(saved_files))
        return {"text": stdout, "status": "SUCCESS"}
    finally:
        shutil.rmtree(req_dir, ignore_errors=True)


def _validate_content_length(header_val: str | None) -> int:
    if not header_val:
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
    direct = headers.get(name)
    if direct is not None:
        return str(direct).strip()
    target_lower = name.lower()
    for key, val in headers.items():
        if key.lower() == target_lower and val is not None:
            return str(val).strip()
    return ""


def _extract_origin_from_url(url_or_origin: str) -> str:
    cleaned = (url_or_origin or "").strip().rstrip("/")
    parsed = urlparse(cleaned) if cleaned else None
    if parsed and parsed.scheme and parsed.netloc:
        return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"
    return ""


def _is_allowed_origin(origin: str | None) -> bool:
    normalized = _extract_origin_from_url(origin or "")
    if not normalized:
        return False
    if normalized in {item.lower() for item in ALLOWED_ORIGINS}:
        return True
    return bool(
        re.match(r"^https://[a-z0-9-]+\.lumen-bookkeeping\.pages\.dev$", normalized)
        or re.match(r"^http://(localhost|127\.0\.0\.1|bookkeeping-web)(:\d+)?$", normalized)
    )


def _verify_prediction_request_security(headers: Mapping[str, str]) -> str | None:
    if AGY_API_SECRET:
        provided_secret = _get_header_case_insensitive(headers, "X-Agy-Proxy-Secret")
        if not provided_secret or not hmac.compare_digest(provided_secret.encode(), AGY_API_SECRET.encode()):
            raise UnauthorizedPredictionRequestError("Unauthorized: valid proxy authentication secret is required.", internal_detail="Missing or invalid X-Agy-Proxy-Secret header")
    client_header = _get_header_case_insensitive(headers, "X-Lumen-Client")
    if client_header != REQUIRED_CLIENT_HEADER_VALUE:
        raise UnauthorizedPredictionRequestError("Unauthorized: prediction endpoint is restricted to the Lumen Bookkeeping application.", internal_detail=f"Missing or invalid X-Lumen-Client header: {client_header!r}")
    raw_origin, raw_referer = _get_header_case_insensitive(headers, "Origin"), _get_header_case_insensitive(headers, "Referer")
    candidate_origin = _extract_origin_from_url(raw_origin) if raw_origin else _extract_origin_from_url(raw_referer)
    if raw_origin or raw_referer:
        if not candidate_origin or not _is_allowed_origin(candidate_origin):
            raise ForbiddenOriginPredictionError("Forbidden: request origin is not authorized to access this service.", internal_detail=f"Rejected untrusted origin={raw_origin!r} referer={raw_referer!r}")
        return candidate_origin
    if REQUIRE_ORIGIN:
        raise ForbiddenOriginPredictionError("Forbidden: request origin header is required.", internal_detail="Missing both Origin and Referer headers while AGY_REQUIRE_ORIGIN is enabled")
    return None


def _resolve_default_state_db_path() -> Path:
    return resolve_default_state_db_path(os.environ.get("LUMEN_STATE_DB_PATH", "").strip())


STATE_REPO: LumenStateRepository | None = None


def get_state_repo() -> LumenStateRepository:
    """Return the active `LumenStateRepository`, initializing it lazily on first access."""
    global STATE_REPO
    if STATE_REPO is None:
        STATE_REPO = LumenStateRepository(_resolve_default_state_db_path(), session_secret=AGY_API_SECRET or None)
    return STATE_REPO


def _resolve_caller_context(headers: Mapping[str, str], repo: LumenStateRepository) -> CallerContext:
    return repo.resolve_caller_context(
        cf_email=_get_header_case_insensitive(headers, "Cf-Access-Authenticated-User-Email"),
        account_header=_get_header_case_insensitive(headers, "X-Lumen-Account"),
        session_header=_get_header_case_insensitive(headers, "X-Lumen-Session"),
    )


def _parse_json_object(body: bytes) -> dict:
    try:
        payload = json.loads((body.decode("utf-8") if body else "{}") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidPredictionRequestError("Request body must be valid UTF-8 JSON.", internal_detail=str(exc)) from exc
    if not isinstance(payload, dict):
        raise InvalidPredictionRequestError("JSON request payload must be an object.")
    return payload


def _handle_state_post(
    body: bytes, repo: LumenStateRepository, caller_ctx: CallerContext, *, captcha_attestation: str | None = None,
) -> dict:
    payload = _parse_json_object(body)
    set_map, remove_list = payload.get("set") or {}, payload.get("remove") or []
    if not isinstance(set_map, dict) or not isinstance(remove_list, list):
        raise InvalidPredictionRequestError("Fields 'set' (object) and 'remove' (list) must have valid types.")
    att = captcha_attestation or (str(payload.get("captchaAttestation") or "") if isinstance(payload.get("captchaAttestation"), str) else None)
    try:
        updated = repo.mutate_scoped_state(
            caller_ctx.account_id, set_map, [str(k) for k in remove_list],
            clear_all=bool(payload.get("clear_all")), caller_context=caller_ctx, captcha_attestation=att,
        )
    except PermissionError as exc:
        raise ForbiddenRoleError(str(exc)) from exc
    return {"status": "ok", "updated": updated}


def _handle_attachments_post(body: bytes, repo: LumenStateRepository, caller_ctx: CallerContext) -> dict:
    payload = _parse_json_object(body)
    items: dict[str, str] = {}
    if isinstance(payload.get("attachments"), dict):
        items.update({str(k): str(v) for k, v in payload["attachments"].items() if v is not None})
    if isinstance(payload.get("key"), str) and isinstance(payload.get("data"), str):
        items[payload["key"]] = payload["data"]
    remove_list = payload.get("remove") or []
    if not isinstance(remove_list, list):
        raise InvalidPredictionRequestError("Field 'remove' must be a list.")
    try:
        updated = repo.put_attachments(items, [str(k) for k in remove_list], account_id=caller_ctx.account_id, caller_context=caller_ctx)
    except PermissionError as exc:
        raise ForbiddenRoleError(str(exc)) from exc
    return {"status": "ok", "updated": updated}


class AgyPredictionHandler(BaseHTTPRequestHandler):
    """HTTP request handler exposing Flowise-compatible `/api/v1/prediction/*`, auth, and persistence endpoints."""

    def _send_json(self, payload: dict, status: int = 200) -> None:
        raw = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Content-Length", str(len(raw)))
        req_origin = _extract_origin_from_url(self.headers.get("Origin", ""))
        if req_origin and _is_allowed_origin(req_origin):
            self.send_header("Access-Control-Allow-Origin", req_origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Lumen-Client, X-Lumen-Account, X-Lumen-Session, X-Lumen-Captcha, X-Agy-Proxy-Secret")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(raw)

    def do_OPTIONS(self) -> None:
        raw_origin = self.headers.get("Origin", "")
        if raw_origin and not _is_allowed_origin(raw_origin):
            return self._send_json(build_error_envelope("forbidden_origin", "Forbidden: request origin is not authorized to access this service."), status=403)
        self._send_json({"status": "ok"}, status=200)

    def _send_bytes(self, raw: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/__vendor__/chart.js":
            return self._send_bytes(CHART_JS_SHIM.encode(), "application/javascript; charset=utf-8")
        if parsed.path in ("/__vendor__/pdf.min.js", "/__vendor__/pdf.worker.min.js"):
            return self._send_bytes(PDF_JS_SHIM.encode(), "application/javascript; charset=utf-8")
        if parsed.path == "/__vendor__/fonts.css":
            return self._send_bytes(b"/* local font shim */\n", "text/css; charset=utf-8")
        if parsed.path in ("/", "/health", "/api/v1/ping") or parsed.path.startswith("/api/v1/prediction/"):
            return self._send_json({"status": "ok", "engine": "agy", "model": AGY_MODEL}, status=200)
        if parsed.path in ("/api/v1/state", "/api/v1/attachments", "/api/v1/auth/session", "/api/v1/auth/captcha-config"):
            try:
                _verify_prediction_request_security(self.headers)
                if parsed.path == "/api/v1/auth/captcha-config":
                    return self._send_json({"ok": True, "provider": "recaptcha", "siteKey": os.environ.get("RECAPTCHA_SITE_KEY", "").strip()}, status=200)
                repo = get_state_repo()
                if parsed.path == "/api/v1/auth/session":
                    self._send_json(repo.resolve_session(cf_email=_get_header_case_insensitive(self.headers, "Cf-Access-Authenticated-User-Email"), account_header=_get_header_case_insensitive(self.headers, "X-Lumen-Account"), session_header=_get_header_case_insensitive(self.headers, "X-Lumen-Session")), status=200)
                elif parsed.path == "/api/v1/state":
                    caller_ctx = _resolve_caller_context(self.headers, repo)
                    self._send_json({"status": "ok", "state": repo.get_scoped_state(caller_ctx.account_id, caller_context=caller_ctx)}, status=200)
                else:
                    caller_ctx = _resolve_caller_context(self.headers, repo)
                    key = (parse_qs(parsed.query).get("key") or [""])[0]
                    self._send_json({"status": "ok", "key": key, "data": repo.get_attachment(key, account_id=caller_ctx.account_id, caller_context=caller_ctx)}, status=200)
            except PredictionServiceError as exc:
                self._send_json(build_error_envelope(exc.error_code, exc.public_message), status=exc.status_code)
            return
        self._send_json(build_error_envelope("not_found", "Endpoint not found."), status=404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/api/"):
            return self._send_json(build_error_envelope("not_found", "Endpoint not found."), status=404)
        try:
            origin = _verify_prediction_request_security(self.headers)
            content_len = _validate_content_length(self.headers.get("Content-Length"))
            body = self.rfile.read(content_len) if content_len > 0 else b""
            repo = get_state_repo()
            if parsed.path == "/api/v1/auth/captcha/verify":
                payload = _parse_json_object(body)
                res = _verify_recaptcha_token(payload.get("token"), secret=os.environ.get("RECAPTCHA_SECRET_KEY", "").strip(), session_secret=repo._session_secret, origin=origin)
                return self._send_json(res, status=int(res.get("status_code") or 200))
            if parsed.path in ("/api/v1/auth/login", "/api/v1/auth/password-reset/request", "/api/v1/auth/reset-request", "/api/v1/auth/password-reset/confirm", "/api/v1/auth/reset-confirm"):
                payload = _parse_json_object(body)
                if parsed.path == "/api/v1/auth/login":
                    res = repo.verify_login(payload.get("email"), payload.get("password"))
                elif parsed.path.endswith("request"):
                    res = repo.request_password_reset(payload.get("email"))
                else:
                    res = repo.confirm_password_reset(payload.get("email"), payload.get("code"), payload.get("newPassword"))
                return self._send_json(res, status=int(res.get("status_code") or 200))
            caller_ctx = _resolve_caller_context(self.headers, repo)
            if parsed.path in ("/api/v1/auth/trial-reminder", "/api/v1/auth/trial-renew", "/api/v1/auth/payment-method"):
                payload = _parse_json_object(body)
                if parsed.path == "/api/v1/auth/payment-method":
                    res = repo.save_payment_method(
                        payload.get("email"), caller_account=caller_ctx.account_id, caller_context=caller_ctx,
                        card_holder_name=payload.get("cardHolderName", ""), card_brand=payload.get("cardBrand", "Card"),
                        card_last4=payload.get("cardLast4", ""), card_expiry=payload.get("cardExpiry", ""),
                        payment_method_token=payload.get("paymentMethodToken", ""), pay_now=payload.get("payNow", False),
                    )
                else:
                    fn = repo.send_trial_renewal_reminder if parsed.path.endswith("trial-reminder") else repo.process_trial_renewal
                    res = fn(payload.get("email"), caller_account=caller_ctx.account_id, caller_context=caller_ctx)
                return self._send_json(res, status=403 if res.get("error") == "Forbidden." else int(res.get("status_code") or 200))
            if parsed.path in ("/api/v1/einvoice/submit", "/api/v1/einvoice/webhook", "/api/v1/einvoice/inbound"):
                if not parsed.path.endswith("webhook") and caller_ctx.role in ("viewer", "unauthenticated"):
                    raise ForbiddenRoleError("Read-only viewer role cannot submit or import e-invoices.")
                payload = _parse_json_object(body)
                try:
                    res = repo.handle_einvoice_webhook(payload) if parsed.path.endswith("webhook") else (repo.receive_inbound_einvoice(payload, caller_account=caller_ctx.account_id, caller_context=caller_ctx) if parsed.path.endswith("inbound") else repo.submit_einvoice(payload, caller_account=caller_ctx.account_id, caller_context=caller_ctx))
                except PermissionError as exc:
                    raise ForbiddenRoleError(str(exc)) from exc
                return self._send_json(res, status=int(res.get("status_code") or 200))
            if parsed.path == "/api/v1/state":
                return self._send_json(_handle_state_post(body, repo, caller_ctx, captcha_attestation=_get_header_case_insensitive(self.headers, "X-Lumen-Captcha") or None), status=200)
            if parsed.path == "/api/v1/attachments":
                return self._send_json(_handle_attachments_post(body, repo, caller_ctx), status=200)
            if not parsed.path.startswith("/api/v1/prediction/"):
                return self._send_json(build_error_envelope("not_found", "Endpoint not found."), status=404)
            if not repo.is_account_ai_enabled(caller_ctx.account_id, raw_account_header=_get_header_case_insensitive(self.headers, "X-Lumen-Account")):
                return self._send_json(build_error_envelope("plan_upgrade_required", "AI features require the Advance, Pro, or Managed Books plan."), status=403)
            content_type = self.headers.get("Content-Type", "")
            question, uploads = _parse_multipart_form_data(content_type, body) if "multipart/form-data" in content_type else _parse_json_prediction_request(body)
            self._send_json(run_agy_prediction(question=question, uploads=uploads), status=200)
        except PredictionServiceError as exc:
            print(f"[agy-error] {exc.error_code}: {exc.internal_detail}", file=sys.stderr, flush=True)
            self._send_json(build_error_envelope(exc.error_code, exc.public_message), status=exc.status_code)
        except Exception as exc:  # noqa: BLE001
            print(f"[agy-error] unexpected: {exc!r}", file=sys.stderr, flush=True)
            self._send_json(build_error_envelope("internal_error", "An unexpected error occurred while processing the prediction request."), status=500)


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), AgyPredictionHandler)
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda s, _f: (print(f"Received signal {s}, shutting down agy prediction service...", flush=True), threading.Thread(target=server.shutdown, daemon=True).start()))
    print(f"Starting agy prediction service on http://{HOST}:{PORT} (model={AGY_MODEL})", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
