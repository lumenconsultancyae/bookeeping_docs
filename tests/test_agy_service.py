"""Unit and HTTP entrypoint integration tests for `agy_service.py`, `features/support_server.py`, and `script.js` contracts."""

from __future__ import annotations

import base64
import hashlib
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, patch
import urllib.error
import urllib.request

import agy_service
from features import config as e2e_config
from features import support_server

DOCS_ROOT = Path(__file__).resolve().parent.parent
APP_ROOT = DOCS_ROOT.parent / "bookkeeping-tool"


def _read_script_js_bundle(app_dir: Path) -> str:
    return "\n".join(
        [(app_dir / "script.js").read_text(encoding="utf-8"), *(p.read_text(encoding="utf-8") for p in sorted(app_dir.glob("app-*.js")))]
    )


class AgyServiceUnitTests(unittest.TestCase):
    """Unit tests for filename sanitization, PDF/image upload handling, request parsing, and subprocess orchestration."""

    def test_sanitize_filename_prevents_dot_traversal_and_prefixes_index(self) -> None:
        self.assertEqual(agy_service._sanitize_filename("..", 0, "image/png"), "0_document_0.png")
        self.assertEqual(agy_service._sanitize_filename(".", 1, "image/jpeg"), "1_document_1.jpg")
        self.assertEqual(agy_service._sanitize_filename("-rf.png", 2, "image/png"), "2_rf.png")
        self.assertEqual(agy_service._sanitize_filename("../../etc/passwd", 3, "image/png"), "3_passwd")

    def test_sanitize_filename_preserves_and_enforces_pdf_extension(self) -> None:
        self.assertEqual(agy_service._sanitize_filename("MFZ-339673 (1).pdf", 0, "application/pdf"), "0_MFZ-339673__1_.pdf")
        self.assertEqual(agy_service._sanitize_filename("..", 0, "application/pdf"), "0_document_0.pdf")
        self.assertEqual(agy_service._sanitize_filename("invoice_without_ext", 0, "application/pdf"), "0_invoice_without_ext.pdf")

    def test_write_uploads_to_dir_saves_raw_pdf_bytes_intact(self) -> None:
        raw_pdf = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"
        b64_data = f"data:application/pdf;base64,{base64.b64encode(raw_pdf).decode('ascii')}"
        uploads = [{"name": "MFZ-339673 (1).pdf", "mime": "application/pdf", "data": b64_data}]
        with tempfile.TemporaryDirectory() as tmp:
            saved = agy_service._write_uploads_to_dir(uploads, Path(tmp))
            self.assertEqual((len(saved), saved[0].name, saved[0].suffix, saved[0].read_bytes()), (1, "0_MFZ-339673__1_.pdf", ".pdf", raw_pdf))

    def test_write_uploads_to_dir_prevents_duplicate_filename_collision(self) -> None:
        raw_png = b"\x89PNG\r\n\x1a\n"
        b64_data = f"data:image/png;base64,{base64.b64encode(raw_png).decode('ascii')}"
        uploads = [
            {"name": "receipt.png", "mime": "image/png", "data": b64_data},
            {"name": "receipt.png", "mime": "image/png", "data": b64_data},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            saved = agy_service._write_uploads_to_dir(uploads, Path(tmp))
            self.assertEqual((len(saved), saved[0].name, saved[1].name), (2, "0_receipt.png", "1_receipt.png"))
            self.assertEqual((saved[0].read_bytes(), saved[1].read_bytes()), (raw_png, raw_png))

    def test_write_uploads_to_dir_rejects_corrupt_base64(self) -> None:
        uploads = [{"name": "bad.png", "mime": "image/png", "data": "data:image/png;base64,!!!not_base64!!!"}]
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(agy_service.InvalidPredictionRequestError):
            agy_service._write_uploads_to_dir(uploads, Path(tmp))

    def test_parse_json_prediction_request_validates_types(self) -> None:
        q, uploads = agy_service._parse_json_prediction_request(
            b'{"question": "Extract invoice", "uploads": [{"name": "a.png", "data": ""}]}'
        )
        self.assertEqual((q, len(uploads)), ("Extract invoice", 1))
        for bad_body in (b"{malformed json", b'["not", "an", "object"]', b'{"question": true}', b'{"question": "ok", "uploads": ["not-a-dict"]}'):
            with self.assertRaises(agy_service.InvalidPredictionRequestError):
                agy_service._parse_json_prediction_request(bad_body)

    def test_parse_multipart_form_data_extracts_question_and_pdf_files(self) -> None:
        boundary = "----TestBoundary12345"
        content_type = f"multipart/form-data; boundary={boundary}"
        body = (
            f'--{boundary}\r\nContent-Disposition: form-data; name="question"\r\n\r\nBANK STATEMENT TEXT\r\n'
            f'--{boundary}\r\nContent-Disposition: form-data; name="files"; filename="statement.pdf"\r\n'
            f"Content-Type: application/pdf\r\n\r\n%PDF-1.7 fake bank statement\r\n--{boundary}--\r\n"
        ).encode("utf-8")
        question, uploads = agy_service._parse_multipart_form_data(content_type, body)
        self.assertEqual((question, len(uploads), uploads[0]["name"], uploads[0]["mime"]), ("BANK STATEMENT TEXT", 1, "statement.pdf", "application/pdf"))

    def test_validate_content_length_bounds(self) -> None:
        self.assertEqual((agy_service._validate_content_length(None), agy_service._validate_content_length("1024")), (0, 1024))
        for bad_len in ("-5", "abc"):
            with self.assertRaises(agy_service.InvalidPredictionRequestError):
                agy_service._validate_content_length(bad_len)
        with self.assertRaises(agy_service.PayloadTooLargeError):
            agy_service._validate_content_length(str(agy_service.MAX_REQUEST_BYTES + 1))

    @patch("agy_service.subprocess.run")
    def test_run_agy_prediction_success_and_cleanup(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["agy"], returncode=0, stdout='{"conversation_id":"conv-123","status":"SUCCESS","response":"```json\\n{\\"total\\": 12520}\\n```"}\n', stderr=""
        )
        raw_pdf = b"%PDF-1.7\n%%EOF"
        b64_pdf = f"data:application/pdf;base64,{base64.b64encode(raw_pdf).decode('ascii')}"
        res = agy_service.run_agy_prediction(
            "Extract supplier invoice", [{"name": "MFZ-339673 (1).pdf", "mime": "application/pdf", "data": b64_pdf}]
        )
        self.assertEqual((res["conversation_id"], res["status"]), ("conv-123", "SUCCESS"))
        self.assertIn("12520", res["text"])
        prompt_arg = mock_run.call_args.args[0][-1]
        for expected in ("0_MFZ-339673__1_.pdf", "Do NOT call `run_command`", "pre-tax net amount"):
            self.assertIn(expected, prompt_arg)
        self.assertFalse(Path(mock_run.call_args.kwargs["cwd"]).exists())

    @patch("agy_service.subprocess.run")
    def test_run_agy_prediction_timeout_raises_typed_error(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["agy", "--secret-path"], timeout=240)
        with self.assertRaises(agy_service.PredictionTimeoutError) as ctx:
            agy_service.run_agy_prediction("Extract bill", [])
        self.assertEqual(ctx.exception.status_code, 504)
        self.assertNotIn("--secret-path", ctx.exception.public_message)

    @patch("agy_service.subprocess.run")
    def test_run_agy_prediction_nonzero_exit_raises_upstream_error(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["agy"], returncode=1, stdout="", stderr="internal stacktrace /root/.gemini/token"
        )
        with self.assertRaises(agy_service.UpstreamPredictionError) as ctx:
            agy_service.run_agy_prediction("Extract bill", [])
        self.assertEqual(ctx.exception.status_code, 502)
        self.assertNotIn("/root/.gemini", ctx.exception.public_message)

    def test_pdf_js_shim_does_not_inject_fake_bank_statement_text(self) -> None:
        self.assertNotIn("Emirates NBD Statement", agy_service.PDF_JS_SHIM)
        self.assertNotIn("DEWA Electricity Bill", agy_service.PDF_JS_SHIM)

    def test_is_allowed_origin_accepts_trusted_origins_and_rejects_unknown_origins(self) -> None:
        for good in (
            "https://bookeeping.lumenconsultancy.net",
            "https://bookkeeping.lumenconsultancy.net",
            "https://lumen-bookkeeping.pages.dev",
            "https://a1b2c3d4.lumen-bookkeeping.pages.dev",
            "http://localhost:9091",
            "http://127.0.0.1:9091",
            "http://bookkeeping-web",
        ):
            self.assertTrue(agy_service._is_allowed_origin(good))
        for bad in ("https://evil.example.com", "https://lumen-bookkeeping.pages.dev.evil.com", "http://attacker.local:9091"):
            self.assertFalse(agy_service._is_allowed_origin(bad))

    def test_verify_prediction_request_security_enforces_client_header_origin_and_shared_secret(self) -> None:
        with self.assertRaises(agy_service.UnauthorizedPredictionRequestError) as ctx:
            agy_service._verify_prediction_request_security({})
        self.assertEqual((ctx.exception.status_code, ctx.exception.error_code), (401, "unauthorized"))
        with self.assertRaises(agy_service.UnauthorizedPredictionRequestError):
            agy_service._verify_prediction_request_security({"X-Lumen-Client": "wrong-client"})
        for bad_hdrs in (
            {"X-Lumen-Client": "lumen-bookkeeping-web", "Origin": "https://evil.example.com"},
            {"X-Lumen-Client": "lumen-bookkeeping-web", "Referer": "https://evil.example.com/attack.html"},
        ):
            with self.assertRaises(agy_service.ForbiddenOriginPredictionError) as origin_ctx:
                agy_service._verify_prediction_request_security(bad_hdrs)
            self.assertEqual((origin_ctx.exception.status_code, origin_ctx.exception.error_code), (403, "forbidden_origin"))
        with patch.object(agy_service, "REQUIRE_ORIGIN", True), self.assertRaises(agy_service.ForbiddenOriginPredictionError):
            agy_service._verify_prediction_request_security({"X-Lumen-Client": "lumen-bookkeeping-web"})
        with patch.object(agy_service, "AGY_API_SECRET", "prod-shared-secret-123"):
            for bad_headers in (
                {"X-Lumen-Client": "lumen-bookkeeping-web", "Origin": "https://lumen-bookkeeping.pages.dev"},
                {"X-Lumen-Client": "lumen-bookkeeping-web", "Origin": "https://lumen-bookkeeping.pages.dev", "X-Agy-Proxy-Secret": "wrong-secret"},
            ):
                with self.assertRaises(agy_service.UnauthorizedPredictionRequestError):
                    agy_service._verify_prediction_request_security(bad_headers)
            agy_service._verify_prediction_request_security(
                {"X-Lumen-Client": "lumen-bookkeeping-web", "Origin": "https://lumen-bookkeeping.pages.dev", "X-Agy-Proxy-Secret": "prod-shared-secret-123"}
            )


class FrontendScriptContractTests(unittest.TestCase):
    """Tests verifying `bookkeeping-tool/script.js` preserves raw PDFs for AI extraction and contains core bugfixes."""

    def test_script_js_sends_raw_pdf_to_ai_instead_of_converting_to_jpeg(self) -> None:
        script_text = _read_script_js_bundle(APP_ROOT)
        for forbidden in ("uploadName = currentFile.name + '.jpg'", "uploadName = custCurrentFile.name + '.jpg'", "uploadName = file.name + '.jpg'"):
            self.assertNotIn(forbidden, script_text)
        self.assertIn("formData.append('files', currentBankFile, currentBankFile.name)", script_text)

    def test_script_js_includes_vat_and_inventory_qty_fixes_and_pretax_line_item_normalization(self) -> None:
        script_text = _read_script_js_bundle(APP_ROOT)
        for expected in (
            "const vat = vatTreatment === 'standard' ? (sub * 0.05) : 0;",
            "if (isNew) itemPayload.qty = 0;",
            "pre-tax net amount",
            "if (pendingSupplierItems.length > 0 && supplierBase.total > 0 && supplierBase.tax > 0)",
        ):
            self.assertIn(expected, script_text)

    def test_script_js_and_pages_function_enforce_application_security_headers(self) -> None:
        script_text = _read_script_js_bundle(APP_ROOT)
        self.assertGreaterEqual(script_text.count("'X-Lumen-Client': 'lumen-bookkeeping-web'"), 4)
        self.assertIn("'X-Lumen-Client': 'lumen-bookkeeping-web'", (APP_ROOT / "expenses.js").read_text(encoding="utf-8"))
        pages_fn = APP_ROOT / "functions" / "api" / "[[path]].js"
        self.assertTrue(pages_fn.is_file())
        fn_text = pages_fn.read_text(encoding="utf-8")
        for token in ("X-Lumen-Client", "X-Agy-Proxy-Secret", "forbidden_origin"):
            self.assertIn(token, fn_text)


class SupportServerAndConfigUnitTests(unittest.TestCase):
    """Unit tests for `features/support_server.py` and `features/config.py`."""

    def test_build_mock_ai_response_branches(self) -> None:
        self.assertIn("Emirates NBD", support_server.build_mock_ai_response("Process BANK STATEMENT")["text"])
        self.assertIn("PC-901", support_server.build_mock_ai_response("Analyze Petty Cash Receipts")["text"])
        self.assertIn("INV-AI-2001", support_server.build_mock_ai_response("Extract CUSTOMER INVOICE")["text"])
        self.assertIn("Gulf Cloud Infrastructure LLC", support_server.build_mock_ai_response("Extract SUPPLIER INVOICE")["text"])

    def test_resolve_default_base_url_respects_explicit_env(self) -> None:
        with patch.dict(os.environ, {"BOOKKEEPING_BASE_URL": "http://custom-host:8088"}):
            self.assertEqual(e2e_config._resolve_default_base_url(), ("custom-host", 8088, "http://custom-host:8088", True))


class AgyHttpEndpointIntegrationTests(unittest.TestCase):
    """Entrypoint HTTP tests for `AgyPredictionHandler` error envelopes and status codes."""

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

    def test_health_and_vendor_endpoints(self) -> None:
        with urllib.request.urlopen(f"{self.base_url}/health", timeout=5) as resp:
            self.assertEqual((resp.status, json.loads(resp.read().decode("utf-8"))["engine"]), (200, "agy"))
        with urllib.request.urlopen(f"{self.base_url}/__vendor__/chart.js", timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("window.Chart", resp.read().decode("utf-8"))

    @patch("agy_service.subprocess.run")
    def test_post_without_client_header_returns_401_unauthorized(self, mock_run: MagicMock) -> None:
        req = urllib.request.Request(f"{self.base_url}/api/v1/prediction/test", data=b'{"question": "Extract"}', headers={"Content-Type": "application/json"}, method="POST")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual((ctx.exception.code, json.loads(ctx.exception.read().decode("utf-8"))["error"]["code"]), (401, "unauthorized"))
        mock_run.assert_not_called()

    @patch("agy_service.subprocess.run")
    def test_post_from_untrusted_origin_returns_403_forbidden_origin(self, mock_run: MagicMock) -> None:
        req = urllib.request.Request(
            f"{self.base_url}/api/v1/prediction/test",
            data=b'{"question": "Extract"}',
            headers={"Content-Type": "application/json", "X-Lumen-Client": "lumen-bookkeeping-web", "Origin": "https://evil.example.com"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(ctx.exception.code, 403)
        self.assertIsNone(ctx.exception.headers.get("Access-Control-Allow-Origin"))
        self.assertEqual(json.loads(ctx.exception.read().decode("utf-8"))["error"]["code"], "forbidden_origin")
        mock_run.assert_not_called()

    @patch("agy_service.subprocess.run")
    def test_post_with_configured_api_secret_enforces_shared_secret(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["agy"], returncode=0, stdout='{"conversation_id":"conv-sec","status":"SUCCESS","response":"```json\\n{}\\n```"}\n', stderr=""
        )
        with patch.object(agy_service, "AGY_API_SECRET", "prod-secret-xyz"):
            req_missing = urllib.request.Request(
                f"{self.base_url}/api/v1/prediction/test",
                data=b'{"question": "Extract"}',
                headers={"Content-Type": "application/json", "X-Lumen-Client": "lumen-bookkeeping-web", "Origin": "https://lumen-bookkeeping.pages.dev"},
                method="POST",
            )
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(req_missing, timeout=5)
            self.assertEqual(ctx.exception.code, 401)
            req_valid = urllib.request.Request(
                f"{self.base_url}/api/v1/prediction/test",
                data=b'{"question": "Extract"}',
                headers={
                    "Content-Type": "application/json",
                    "X-Lumen-Client": "lumen-bookkeeping-web",
                    "Origin": "https://lumen-bookkeeping.pages.dev",
                    "X-Agy-Proxy-Secret": "prod-secret-xyz",
                },
                method="POST",
            )
            with urllib.request.urlopen(req_valid, timeout=5) as resp:
                self.assertEqual((resp.status, resp.headers.get("Access-Control-Allow-Origin")), (200, "https://lumen-bookkeeping.pages.dev"))

    def test_invalid_json_returns_400_structured_error_envelope(self) -> None:
        req = urllib.request.Request(
            f"{self.base_url}/api/v1/prediction/test",
            data=b"{bad json",
            headers={"Content-Type": "application/json", "X-Lumen-Client": "lumen-bookkeeping-web", "Origin": "http://localhost:9091"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(ctx.exception.code, 400)
        body = json.loads(ctx.exception.read().decode("utf-8"))
        self.assertEqual(body["error"]["code"], "invalid_request")
        self.assertIn("text", body)

    def test_non_string_question_returns_400(self) -> None:
        req = urllib.request.Request(
            f"{self.base_url}/api/v1/prediction/test",
            data=b'{"question": true}',
            headers={"Content-Type": "application/json", "X-Lumen-Client": "lumen-bookkeeping-web", "Origin": "http://localhost:9091"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual((ctx.exception.code, json.loads(ctx.exception.read().decode("utf-8"))["error"]["code"]), (400, "invalid_request"))

    @patch("agy_service.subprocess.run")
    def test_subprocess_timeout_returns_504_without_leaking_internals(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["agy", "/tmp/secret_req"], timeout=240)
        req = urllib.request.Request(
            f"{self.base_url}/api/v1/prediction/test",
            data=b'{"question": "Extract"}',
            headers={"Content-Type": "application/json", "X-Lumen-Client": "lumen-bookkeeping-web", "Origin": "http://localhost:9091"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=5)
        raw_resp = ctx.exception.read().decode("utf-8")
        self.assertNotIn("/tmp/secret_req", raw_resp)
        self.assertEqual((ctx.exception.code, json.loads(raw_resp)["error"]["code"]), (504, "prediction_timeout"))

    @patch("agy_service.subprocess.run")
    def test_options_cors_get_vendor_404_multipart_post_and_500_error_branches(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(args=["agy"], returncode=0, stdout="Plain text stdout fallback", stderr="")
        req_opt_ok = urllib.request.Request(f"{self.base_url}/api/v1/prediction/test", headers={"Origin": "http://localhost:9091"}, method="OPTIONS")
        with urllib.request.urlopen(req_opt_ok, timeout=5) as resp:
            self.assertEqual((resp.status, resp.headers.get("Access-Control-Allow-Origin")), (200, "http://localhost:9091"))
        req_opt_bad = urllib.request.Request(f"{self.base_url}/api/v1/prediction/test", headers={"Origin": "https://attacker.example.com"}, method="OPTIONS")
        with self.assertRaises(urllib.error.HTTPError) as opt_ctx:
            urllib.request.urlopen(req_opt_bad, timeout=5)
        self.assertEqual(opt_ctx.exception.code, 403)
        for path in ("/__vendor__/pdf.min.js", "/__vendor__/fonts.css", "/api/v1/ping"):
            with urllib.request.urlopen(f"{self.base_url}{path}", timeout=5) as resp:
                self.assertEqual(resp.status, 200)
        with self.assertRaises(urllib.error.HTTPError) as get_404:
            urllib.request.urlopen(f"{self.base_url}/does-not-exist", timeout=5)
        self.assertEqual(get_404.exception.code, 404)
        req_post_404 = urllib.request.Request(f"{self.base_url}/unknown", data=b"{}", headers={"Content-Type": "application/json"}, method="POST")
        with self.assertRaises(urllib.error.HTTPError) as post_404:
            urllib.request.urlopen(req_post_404, timeout=5)
        self.assertEqual(post_404.exception.code, 404)
        boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
        mp_body = f'--{boundary}\r\nContent-Disposition: form-data; name="question"\r\n\r\nHello conversational prompt\r\n--{boundary}--\r\n'.encode("utf-8")
        req_mp = urllib.request.Request(
            f"{self.base_url}/api/v1/prediction/test",
            data=mp_body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}", "X-Lumen-Client": "lumen-bookkeeping-web", "Origin": "http://localhost:9091"},
            method="POST",
        )
        with urllib.request.urlopen(req_mp, timeout=5) as resp_mp:
            self.assertEqual((resp_mp.status, json.loads(resp_mp.read().decode("utf-8"))["text"]), (200, "Plain text stdout fallback"))
        mock_run.side_effect = RuntimeError("unexpected boom")
        req_500 = urllib.request.Request(
            f"{self.base_url}/api/v1/prediction/test",
            data=b'{"question": "extract json"}',
            headers={"Content-Type": "application/json", "X-Lumen-Client": "lumen-bookkeeping-web", "Origin": "http://localhost:9091"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx_500:
            urllib.request.urlopen(req_500, timeout=5)
        self.assertEqual((ctx_500.exception.code, json.loads(ctx_500.exception.read().decode("utf-8"))["error"]["code"]), (500, "internal_error"))

    def test_state_and_attachments_persistence_endpoints_and_local_config_exclusion(self) -> None:
        expected_digest = hashlib.pbkdf2_hmac("sha256", b"LumenAdmin2026", b"4c756d656e41646d696e53616c743236", 120000).hex()
        self.assertEqual(
            agy_service._compute_password_hash("LumenAdmin2026", "4c756d656e41646d696e53616c743236"),
            f"pbkdf2_sha256$120000${expected_digest}",
        )
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "isolated_test_state.sqlite3"
            self.assertNotEqual(db_path.resolve(), Path("/root/.gemini/lumen_books_state.sqlite3").resolve())
            repo = agy_service.LumenStateRepository(db_path)
            with patch.object(agy_service, "STATE_REPO", repo):
                base_headers = {"Content-Type": "application/json", "X-Lumen-Client": "lumen-bookkeeping-web", "Origin": "http://localhost:9091"}
                owner_headers = {**base_headers, "X-Lumen-Account": "owner"}

                unauth_post = urllib.request.Request(
                    f"{self.base_url}/api/v1/state",
                    data=json.dumps({"set": {"profile:p1::bookkeeping_history_v2": '[{"id":"unauth"}]'}}).encode("utf-8"),
                    headers=base_headers,
                    method="POST",
                )
                with urllib.request.urlopen(unauth_post, timeout=5) as resp:
                    self.assertEqual(json.loads(resp.read().decode("utf-8"))["updated"], 0)

                tenant_hash = agy_service._compute_password_hash("TenantPass123", "salttenant1")
                post_state = urllib.request.Request(
                    f"{self.base_url}/api/v1/state",
                    data=json.dumps({
                        "set": {
                            "lumen_accounts": json.dumps({
                                "acc-1": {"email": "u@example.com", "status": "active", "salt": "salttenant1", "passwordHash": tenant_hash},
                                "acc-susp": {"email": "suspended@example.com", "status": "suspended", "salt": "salttenant1", "passwordHash": tenant_hash},
                            }),
                            "lumen_profiles": json.dumps([{"id": "p1", "name": "Tenant 1", "accountId": "acc-1"}]),
                            "profile:p1::bookkeeping_history_v2": '[{"id":"inv-1"}]',
                            "lumen_admin_credentials": json.dumps({"salt": agy_service.DEFAULT_ADMIN_SALT, "passwordHash": agy_service.DEFAULT_ADMIN_HASH}),
                            "lumen_lang": "ar",
                            "lumen_sidebar_collapsed": "1",
                            "lumen_table_page_size:ledgerBody": "25",
                            "lumen_current_account": "acc-1",
                        }
                    }).encode("utf-8"),
                    headers=owner_headers,
                    method="POST",
                )
                with urllib.request.urlopen(post_state, timeout=5) as resp:
                    self.assertEqual(json.loads(resp.read().decode("utf-8"))["updated"], 4)

                get_state = urllib.request.Request(f"{self.base_url}/api/v1/state", headers=owner_headers, method="GET")
                with urllib.request.urlopen(get_state, timeout=5) as resp:
                    state = json.loads(resp.read().decode("utf-8"))["state"]
                    self.assertIn("lumen_accounts", state)
                    self.assertIn("profile:p1::bookkeeping_history_v2", state)
                    self.assertNotIn("lumen_admin_credentials", state)
                    for excluded in ("lumen_lang", "lumen_sidebar_collapsed", "lumen_table_page_size:ledgerBody", "lumen_current_account"):
                        self.assertNotIn(excluded, state)

                post_att = urllib.request.Request(
                    f"{self.base_url}/api/v1/attachments",
                    data=json.dumps({
                        "key": "p1::inv-1",
                        "data": "data:application/pdf;base64,JVBERi0xLjc=",
                        "attachments": {"p1::inv-2": "data:image/png;base64,iVBORw0KGgo="},
                    }).encode("utf-8"),
                    headers=owner_headers,
                    method="POST",
                )
                with urllib.request.urlopen(post_att, timeout=5) as resp:
                    self.assertEqual(json.loads(resp.read().decode("utf-8"))["updated"], 2)

                get_att = urllib.request.Request(f"{self.base_url}/api/v1/attachments?key=p1%3A%3Ainv-1", headers=owner_headers, method="GET")
                with urllib.request.urlopen(get_att, timeout=5) as resp:
                    self.assertEqual(json.loads(resp.read().decode("utf-8"))["data"], "data:application/pdf;base64,JVBERi0xLjc=")

                for email, expected_ok, expected_acc in (
                    ("admin@lumenconsultancy.net", True, "owner"),
                    ("u@example.com", True, "acc-1"),
                    ("suspended@example.com", False, None),
                ):
                    pwd = "LumenAdmin2026" if email == "admin@lumenconsultancy.net" else "TenantPass123"
                    login_req = urllib.request.Request(
                        f"{self.base_url}/api/v1/auth/login",
                        data=json.dumps({"email": email, "password": pwd}).encode("utf-8"),
                        headers=base_headers,
                        method="POST",
                    )
                    with urllib.request.urlopen(login_req, timeout=5) as resp:
                        login_res = json.loads(resp.read().decode("utf-8"))
                        self.assertEqual(login_res["ok"], expected_ok)
                        if expected_ok:
                            self.assertEqual(login_res["accountId"], expected_acc)
                            self.assertTrue(str(login_res["sessionToken"]).startswith(f"sess.{expected_acc}."))

                for cf_email, expected_auth, expected_acc in (
                    ("admin@lumenconsultancy.net", True, "owner"),
                    ("u@example.com", True, "acc-1"),
                    ("suspended@example.com", False, None),
                ):
                    cf_req = urllib.request.Request(
                        f"{self.base_url}/api/v1/auth/session",
                        headers={**base_headers, "Cf-Access-Authenticated-User-Email": cf_email},
                        method="GET",
                    )
                    with urllib.request.urlopen(cf_req, timeout=5) as resp:
                        sess_res = json.loads(resp.read().decode("utf-8"))
                        self.assertEqual((sess_res["authenticated"], sess_res["accountId"]), (expected_auth, expected_acc))

                for bad_url, bad_body in (
                    (f"{self.base_url}/api/v1/state", b'{"set": "not-a-dict"}'),
                    (f"{self.base_url}/api/v1/attachments", b'{"remove": "not-a-list"}'),
                ):
                    bad_req = urllib.request.Request(bad_url, data=bad_body, headers=owner_headers, method="POST")
                    with self.assertRaises(urllib.error.HTTPError) as bad_ctx:
                        urllib.request.urlopen(bad_req, timeout=5)
                    self.assertEqual(bad_ctx.exception.code, 400)

                repo.mutate_state({}, ["profile:p1::bookkeeping_history_v2"])
                self.assertNotIn("profile:p1::bookkeeping_history_v2", repo.get_all_state())
                repo.put_attachments({}, ["p1::inv-1"], account_id="owner")
                self.assertIsNone(repo.get_attachment("p1::inv-1", account_id="owner"))
                repo.mutate_state({}, [], clear_all=True)
                self.assertEqual(repo.get_all_state(), {})


if __name__ == "__main__":
    unittest.main()
