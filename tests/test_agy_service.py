"""Unit and HTTP entrypoint integration tests for `agy_service.py`, `features/support_server.py`, and `script.js` contracts."""
from __future__ import annotations
import base64
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
    return "\n".join([(app_dir / "script.js").read_text(encoding="utf-8"), *(p.read_text(encoding="utf-8") for p in sorted(app_dir.glob("app-*.js")))])
class AgyServiceUnitTests(unittest.TestCase):
    """Unit tests for filename sanitization, PDF/image upload handling, request parsing, and subprocess orchestration."""
    def test_sanitize_filename_prevents_dot_traversal_and_prefixes_index(self) -> None:
        self.assertEqual(agy_service._sanitize_filename("..", 0, "image/png"), "0_document_0.png")
        self.assertEqual(agy_service._sanitize_filename(".", 1, "image/jpeg"), "1_document_1.jpg")
        self.assertEqual(agy_service._sanitize_filename("-rf.png", 2, "image/png"), "2_rf.png")
        self.assertEqual(
            agy_service._sanitize_filename("../../etc/passwd", 3, "image/png"),
            "3_passwd",
        )
    def test_sanitize_filename_preserves_and_enforces_pdf_extension(self) -> None:
        self.assertEqual(
            agy_service._sanitize_filename("MFZ-339673 (1).pdf", 0, "application/pdf"),
            "0_MFZ-339673__1_.pdf",
        )
        self.assertEqual(
            agy_service._sanitize_filename("..", 0, "application/pdf"),
            "0_document_0.pdf",
        )
        self.assertEqual(
            agy_service._sanitize_filename("invoice_without_ext", 0, "application/pdf"),
            "0_invoice_without_ext.pdf",
        )
    def test_write_uploads_to_dir_saves_raw_pdf_bytes_intact(self) -> None:
        raw_pdf = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"
        b64_data = f"data:application/pdf;base64,{base64.b64encode(raw_pdf).decode('ascii')}"
        uploads = [
            {
                "name": "MFZ-339673 (1).pdf",
                "mime": "application/pdf",
                "data": b64_data,
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            target_dir = Path(tmp)
            saved = agy_service._write_uploads_to_dir(uploads, target_dir)
            self.assertEqual(len(saved), 1)
            self.assertEqual(saved[0].name, "0_MFZ-339673__1_.pdf")
            self.assertEqual(saved[0].suffix, ".pdf")
            self.assertEqual(saved[0].read_bytes(), raw_pdf)
    def test_write_uploads_to_dir_prevents_duplicate_filename_collision(self) -> None:
        raw_png = b"\x89PNG\r\n\x1a\n"
        b64_data = f"data:image/png;base64,{base64.b64encode(raw_png).decode('ascii')}"
        uploads = [
            {"name": "receipt.png", "mime": "image/png", "data": b64_data},
            {"name": "receipt.png", "mime": "image/png", "data": b64_data},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            target_dir = Path(tmp)
            saved = agy_service._write_uploads_to_dir(uploads, target_dir)
            self.assertEqual(len(saved), 2)
            self.assertNotEqual(saved[0], saved[1])
            self.assertEqual(saved[0].name, "0_receipt.png")
            self.assertEqual(saved[1].name, "1_receipt.png")
            self.assertEqual(saved[0].read_bytes(), raw_png)
            self.assertEqual(saved[1].read_bytes(), raw_png)
    def test_write_uploads_to_dir_rejects_corrupt_base64(self) -> None:
        uploads = [{"name": "bad.png", "mime": "image/png", "data": "data:image/png;base64,!!!not_base64!!!"}]
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(agy_service.InvalidPredictionRequestError):
                agy_service._write_uploads_to_dir(uploads, Path(tmp))
    def test_parse_json_prediction_request_validates_types(self) -> None:
        q, uploads = agy_service._parse_json_prediction_request(
            b'{"question": "Extract invoice", "uploads": [{"name": "a.png", "data": ""}]}'
        )
        self.assertEqual(q, "Extract invoice")
        self.assertEqual(len(uploads), 1)
        with self.assertRaises(agy_service.InvalidPredictionRequestError):
            agy_service._parse_json_prediction_request(b"{malformed json")
        with self.assertRaises(agy_service.InvalidPredictionRequestError):
            agy_service._parse_json_prediction_request(b'["not", "an", "object"]')
        with self.assertRaises(agy_service.InvalidPredictionRequestError):
            agy_service._parse_json_prediction_request(b'{"question": true}')
        with self.assertRaises(agy_service.InvalidPredictionRequestError):
            agy_service._parse_json_prediction_request(b'{"question": "ok", "uploads": ["not-a-dict"]}')
    def test_parse_multipart_form_data_extracts_question_and_pdf_files(self) -> None:
        boundary = "----TestBoundary12345"
        content_type = f"multipart/form-data; boundary={boundary}"
        body = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="question"\r\n\r\n'
            "BANK STATEMENT TEXT\r\n"
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="files"; filename="statement.pdf"\r\n'
            "Content-Type: application/pdf\r\n\r\n"
            "%PDF-1.7 fake bank statement\r\n"
            f"--{boundary}--\r\n"
        ).encode("utf-8")
        question, uploads = agy_service._parse_multipart_form_data(content_type, body)
        self.assertEqual(question, "BANK STATEMENT TEXT")
        self.assertEqual(len(uploads), 1)
        self.assertEqual(uploads[0]["name"], "statement.pdf")
        self.assertEqual(uploads[0]["mime"], "application/pdf")
    def test_validate_content_length_bounds(self) -> None:
        self.assertEqual(agy_service._validate_content_length(None), 0)
        self.assertEqual(agy_service._validate_content_length("1024"), 1024)
        with self.assertRaises(agy_service.InvalidPredictionRequestError):
            agy_service._validate_content_length("-5")
        with self.assertRaises(agy_service.InvalidPredictionRequestError):
            agy_service._validate_content_length("abc")
        with self.assertRaises(agy_service.PayloadTooLargeError):
            agy_service._validate_content_length(str(agy_service.MAX_REQUEST_BYTES + 1))
    @patch("agy_service.subprocess.run")
    def test_run_agy_prediction_success_and_cleanup(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["agy"],
            returncode=0,
            stdout='{"conversation_id":"conv-123","status":"SUCCESS","response":"```json\\n{\\"total\\": 12520}\\n```"}\n',
            stderr="",
        )
        raw_pdf = b"%PDF-1.7\n%%EOF"
        b64_pdf = f"data:application/pdf;base64,{base64.b64encode(raw_pdf).decode('ascii')}"
        res = agy_service.run_agy_prediction(
            "Extract supplier invoice",
            [{"name": "MFZ-339673 (1).pdf", "mime": "application/pdf", "data": b64_pdf}],
        )
        self.assertEqual(res["conversation_id"], "conv-123")
        self.assertEqual(res["status"], "SUCCESS")
        self.assertIn("12520", res["text"])
        called_cmd = mock_run.call_args.args[0]
        prompt_arg = called_cmd[-1]
        self.assertIn("0_MFZ-339673__1_.pdf", prompt_arg)
        self.assertIn("Do NOT call `run_command`", prompt_arg)
        self.assertIn("pre-tax net amount", prompt_arg)
        called_kwargs = mock_run.call_args.kwargs
        req_cwd = Path(called_kwargs["cwd"])
        self.assertFalse(req_cwd.exists(), "Temporary request directory must be deleted after execution")
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
            args=["agy"],
            returncode=1,
            stdout="",
            stderr="internal stacktrace /root/.gemini/token",
        )
        with self.assertRaises(agy_service.UpstreamPredictionError) as ctx:
            agy_service.run_agy_prediction("Extract bill", [])
        self.assertEqual(ctx.exception.status_code, 502)
        self.assertNotIn("/root/.gemini", ctx.exception.public_message)
    def test_pdf_js_shim_does_not_inject_fake_bank_statement_text(self) -> None:
        self.assertNotIn("Emirates NBD Statement", agy_service.PDF_JS_SHIM)
        self.assertNotIn("DEWA Electricity Bill", agy_service.PDF_JS_SHIM)
    def test_is_allowed_origin_accepts_trusted_origins_and_rejects_unknown_origins(self) -> None:
        self.assertTrue(agy_service._is_allowed_origin("https://bookeeping.lumenconsultancy.net"))
        self.assertTrue(agy_service._is_allowed_origin("https://bookkeeping.lumenconsultancy.net"))
        self.assertTrue(agy_service._is_allowed_origin("https://lumen-bookkeeping.pages.dev"))
        self.assertTrue(agy_service._is_allowed_origin("https://a1b2c3d4.lumen-bookkeeping.pages.dev"))
        self.assertTrue(agy_service._is_allowed_origin("http://localhost:9091"))
        self.assertTrue(agy_service._is_allowed_origin("http://127.0.0.1:9091"))
        self.assertTrue(agy_service._is_allowed_origin("http://bookkeeping-web"))
        self.assertFalse(agy_service._is_allowed_origin("https://evil.example.com"))
        self.assertFalse(agy_service._is_allowed_origin("https://lumen-bookkeeping.pages.dev.evil.com"))
        self.assertFalse(agy_service._is_allowed_origin("http://attacker.local:9091"))
    def test_verify_prediction_request_security_enforces_client_header_origin_and_shared_secret(self) -> None:
        with self.assertRaises(agy_service.UnauthorizedPredictionRequestError) as ctx:
            agy_service._verify_prediction_request_security({})
        self.assertEqual(ctx.exception.status_code, 401)
        self.assertEqual(ctx.exception.error_code, "unauthorized")
        with self.assertRaises(agy_service.UnauthorizedPredictionRequestError):
            agy_service._verify_prediction_request_security({"X-Lumen-Client": "wrong-client"})
        with self.assertRaises(agy_service.ForbiddenOriginPredictionError) as origin_ctx:
            agy_service._verify_prediction_request_security(
                {
                    "X-Lumen-Client": "lumen-bookkeeping-web",
                    "Origin": "https://evil.example.com",
                }
            )
        self.assertEqual(origin_ctx.exception.status_code, 403)
        self.assertEqual(origin_ctx.exception.error_code, "forbidden_origin")
        with self.assertRaises(agy_service.ForbiddenOriginPredictionError):
            agy_service._verify_prediction_request_security(
                {
                    "X-Lumen-Client": "lumen-bookkeeping-web",
                    "Referer": "https://evil.example.com/attack.html",
                }
            )
        with patch.object(agy_service, "REQUIRE_ORIGIN", True):
            with self.assertRaises(agy_service.ForbiddenOriginPredictionError):
                agy_service._verify_prediction_request_security(
                    {"X-Lumen-Client": "lumen-bookkeeping-web"}
                )
        with patch.object(agy_service, "AGY_API_SECRET", "prod-shared-secret-123"):
            with self.assertRaises(agy_service.UnauthorizedPredictionRequestError):
                agy_service._verify_prediction_request_security(
                    {
                        "X-Lumen-Client": "lumen-bookkeeping-web",
                        "Origin": "https://lumen-bookkeeping.pages.dev",
                    }
                )
            with self.assertRaises(agy_service.UnauthorizedPredictionRequestError):
                agy_service._verify_prediction_request_security(
                    {
                        "X-Lumen-Client": "lumen-bookkeeping-web",
                        "Origin": "https://lumen-bookkeeping.pages.dev",
                        "X-Agy-Proxy-Secret": "wrong-secret",
                    }
                )
            agy_service._verify_prediction_request_security(
                {
                    "X-Lumen-Client": "lumen-bookkeeping-web",
                    "Origin": "https://lumen-bookkeeping.pages.dev",
                    "X-Agy-Proxy-Secret": "prod-shared-secret-123",
                }
            )
class FrontendScriptContractTests(unittest.TestCase):
    """Tests verifying `bookkeeping-tool/script.js` preserves raw PDFs for AI extraction and contains core bugfixes."""
    def test_script_js_sends_raw_pdf_to_ai_instead_of_converting_to_jpeg(self) -> None:
        script_text = _read_script_js_bundle(APP_ROOT)
        self.assertNotIn("uploadName = currentFile.name + '.jpg'", script_text)
        self.assertNotIn("uploadName = custCurrentFile.name + '.jpg'", script_text)
        self.assertNotIn("uploadName = file.name + '.jpg'", script_text)
        self.assertIn("formData.append('files', currentBankFile, currentBankFile.name)", script_text)
    def test_script_js_includes_vat_and_inventory_qty_fixes_and_pretax_line_item_normalization(self) -> None:
        script_text = _read_script_js_bundle(APP_ROOT)
        self.assertIn(
            "const vat = vatTreatment === 'standard' ? (sub * 0.05) : 0;",
            script_text,
        )
        self.assertIn("if (isNew) itemPayload.qty = 0;", script_text)
        self.assertIn("pre-tax net amount", script_text)
        self.assertIn(
            "if (pendingSupplierItems.length > 0 && supplierBase.total > 0 && supplierBase.tax > 0)",
            script_text,
        )
    def test_script_js_and_pages_function_enforce_application_security_headers(self) -> None:
        script_text = _read_script_js_bundle(APP_ROOT)
        self.assertGreaterEqual(
            script_text.count("'X-Lumen-Client': 'lumen-bookkeeping-web'"),
            4,
            "All 4 AI prediction fetch calls in script.js must include X-Lumen-Client header",
        )
        expenses_text = (APP_ROOT / "expenses.js").read_text(encoding="utf-8")
        self.assertIn(
            "'X-Lumen-Client': 'lumen-bookkeeping-web'",
            expenses_text,
            "AI receipt upload fetch call in expenses.js must include X-Lumen-Client header",
        )
        pages_fn = APP_ROOT / "functions" / "api" / "[[path]].js"
        self.assertTrue(pages_fn.is_file(), "Cloudflare Pages Function proxy must exist in bookkeeping-tool/functions/api/[[path]].js")
        fn_text = pages_fn.read_text(encoding="utf-8")
        self.assertIn("X-Lumen-Client", fn_text)
        self.assertIn("X-Agy-Proxy-Secret", fn_text)
        self.assertIn("forbidden_origin", fn_text)
class SupportServerAndConfigUnitTests(unittest.TestCase):
    """Unit tests for `features/support_server.py` and `features/config.py`."""
    def test_build_mock_ai_response_branches(self) -> None:
        bank = support_server.build_mock_ai_response("Process BANK STATEMENT")
        self.assertIn("Emirates NBD", bank["text"])
        petty = support_server.build_mock_ai_response("Analyze Petty Cash Receipts")
        self.assertIn("PC-901", petty["text"])
        cust = support_server.build_mock_ai_response("Extract CUSTOMER INVOICE")
        self.assertIn("INV-AI-2001", cust["text"])
        sup = support_server.build_mock_ai_response("Extract SUPPLIER INVOICE")
        self.assertIn("Gulf Cloud Infrastructure LLC", sup["text"])
    def test_resolve_default_base_url_respects_explicit_env(self) -> None:
        with patch.dict(os.environ, {"BOOKKEEPING_BASE_URL": "http://custom-host:8088"}):
            host, port, url, using_external = e2e_config._resolve_default_base_url()
            self.assertEqual(host, "custom-host")
            self.assertEqual(port, 8088)
            self.assertEqual(url, "http://custom-host:8088")
            self.assertTrue(using_external)
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
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data["engine"], "agy")
        with urllib.request.urlopen(f"{self.base_url}/__vendor__/chart.js", timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("window.Chart", resp.read().decode("utf-8"))
    @patch("agy_service.subprocess.run")
    def test_post_without_client_header_returns_401_unauthorized(self, mock_run: MagicMock) -> None:
        req = urllib.request.Request(
            f"{self.base_url}/api/v1/prediction/test",
            data=b'{"question": "Extract"}',
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(ctx.exception.code, 401)
        body = json.loads(ctx.exception.read().decode("utf-8"))
        self.assertEqual(body["error"]["code"], "unauthorized")
        mock_run.assert_not_called()
    @patch("agy_service.subprocess.run")
    def test_post_from_untrusted_origin_returns_403_forbidden_origin(self, mock_run: MagicMock) -> None:
        req = urllib.request.Request(
            f"{self.base_url}/api/v1/prediction/test",
            data=b'{"question": "Extract"}',
            headers={
                "Content-Type": "application/json",
                "X-Lumen-Client": "lumen-bookkeeping-web",
                "Origin": "https://evil.example.com",
            },
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(ctx.exception.code, 403)
        self.assertIsNone(ctx.exception.headers.get("Access-Control-Allow-Origin"))
        body = json.loads(ctx.exception.read().decode("utf-8"))
        self.assertEqual(body["error"]["code"], "forbidden_origin")
        mock_run.assert_not_called()
    @patch("agy_service.subprocess.run")
    def test_post_with_configured_api_secret_enforces_shared_secret(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["agy"],
            returncode=0,
            stdout='{"conversation_id":"conv-sec","status":"SUCCESS","response":"```json\\n{}\\n```"}\n',
            stderr="",
        )
        with patch.object(agy_service, "AGY_API_SECRET", "prod-secret-xyz"):
            req_missing = urllib.request.Request(
                f"{self.base_url}/api/v1/prediction/test",
                data=b'{"question": "Extract"}',
                headers={
                    "Content-Type": "application/json",
                    "X-Lumen-Client": "lumen-bookkeeping-web",
                    "Origin": "https://lumen-bookkeeping.pages.dev",
                },
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
                self.assertEqual(resp.status, 200)
                self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), "https://lumen-bookkeeping.pages.dev")
    def test_invalid_json_returns_400_structured_error_envelope(self) -> None:
        req = urllib.request.Request(
            f"{self.base_url}/api/v1/prediction/test",
            data=b"{bad json",
            headers={
                "Content-Type": "application/json",
                "X-Lumen-Client": "lumen-bookkeeping-web",
                "Origin": "http://localhost:9091",
            },
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
            headers={
                "Content-Type": "application/json",
                "X-Lumen-Client": "lumen-bookkeeping-web",
                "Origin": "http://localhost:9091",
            },
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(ctx.exception.code, 400)
        body = json.loads(ctx.exception.read().decode("utf-8"))
        self.assertEqual(body["error"]["code"], "invalid_request")
    @patch("agy_service.subprocess.run")
    def test_subprocess_timeout_returns_504_without_leaking_internals(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["agy", "/tmp/secret_req"], timeout=240)
        req = urllib.request.Request(
            f"{self.base_url}/api/v1/prediction/test",
            data=b'{"question": "Extract"}',
            headers={
                "Content-Type": "application/json",
                "X-Lumen-Client": "lumen-bookkeeping-web",
                "Origin": "http://localhost:9091",
            },
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(ctx.exception.code, 504)
        raw_resp = ctx.exception.read().decode("utf-8")
        self.assertNotIn("/tmp/secret_req", raw_resp)
        body = json.loads(raw_resp)
        self.assertEqual(body["error"]["code"], "prediction_timeout")
    @patch("agy_service.subprocess.run")
    def test_options_cors_get_vendor_404_multipart_post_and_500_error_branches(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["agy"],
            returncode=0,
            stdout="Plain text stdout fallback",
            stderr="",
        )
        req_opt_ok = urllib.request.Request(
            f"{self.base_url}/api/v1/prediction/test",
            headers={"Origin": "http://localhost:9091"},
            method="OPTIONS",
        )
        with urllib.request.urlopen(req_opt_ok, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), "http://localhost:9091")
        req_opt_bad = urllib.request.Request(
            f"{self.base_url}/api/v1/prediction/test",
            headers={"Origin": "https://attacker.example.com"},
            method="OPTIONS",
        )
        with self.assertRaises(urllib.error.HTTPError) as opt_ctx:
            urllib.request.urlopen(req_opt_bad, timeout=5)
        self.assertEqual(opt_ctx.exception.code, 403)
        for path in ("/__vendor__/pdf.min.js", "/__vendor__/fonts.css", "/api/v1/ping"):
            with urllib.request.urlopen(f"{self.base_url}{path}", timeout=5) as resp:
                self.assertEqual(resp.status, 200)
        with self.assertRaises(urllib.error.HTTPError) as get_404:
            urllib.request.urlopen(f"{self.base_url}/does-not-exist", timeout=5)
        self.assertEqual(get_404.exception.code, 404)
        req_post_404 = urllib.request.Request(
            f"{self.base_url}/unknown",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as post_404:
            urllib.request.urlopen(req_post_404, timeout=5)
        self.assertEqual(post_404.exception.code, 404)
        boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
        mp_body = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="question"\r\n\r\n'
            "Hello conversational prompt\r\n"
            f"--{boundary}--\r\n"
        ).encode("utf-8")
        req_mp = urllib.request.Request(
            f"{self.base_url}/api/v1/prediction/test",
            data=mp_body,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "X-Lumen-Client": "lumen-bookkeeping-web",
                "Origin": "http://localhost:9091",
            },
            method="POST",
        )
        with urllib.request.urlopen(req_mp, timeout=5) as resp_mp:
            self.assertEqual(resp_mp.status, 200)
            data_mp = json.loads(resp_mp.read().decode("utf-8"))
            self.assertEqual(data_mp["text"], "Plain text stdout fallback")
        mock_run.side_effect = RuntimeError("unexpected boom")
        req_500 = urllib.request.Request(
            f"{self.base_url}/api/v1/prediction/test",
            data=b'{"question": "extract json"}',
            headers={
                "Content-Type": "application/json",
                "X-Lumen-Client": "lumen-bookkeeping-web",
                "Origin": "http://localhost:9091",
            },
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx_500:
            urllib.request.urlopen(req_500, timeout=5)
        self.assertEqual(ctx_500.exception.code, 500)
        body_500 = json.loads(ctx_500.exception.read().decode("utf-8"))
        self.assertEqual(body_500["error"]["code"], "internal_error")
if __name__ == "__main__":
    unittest.main()
