import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import agy_service
from features import support_server
from state_auth_billing import (
    PLATFORM_INTEGRATIONS_KEY,
    PLATFORM_SECRETS_KEY,
    CallerContext,
    collect_reserved_emails,
    merge_team_users,
)
from state_repository import LumenStateRepository, compute_password_hash


class TestTeamUsersStateRepository(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = LumenStateRepository(Path(self._tmp.name) / "state.db")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _seed_account(self, acc_id: str, email: str, plan: str = "basic", team_users: list | None = None) -> None:
        salt = "a" * 32
        pw_hash = compute_password_hash("Password123", salt)
        accounts = {
            acc_id: {
                "email": email,
                "companyName": "Lumen Client LLC",
                "plan": plan,
                "status": "active",
                "salt": salt,
                "passwordHash": pw_hash,
                "teamUsers": team_users or [],
            }
        }
        profiles = [{"id": f"prof-{acc_id}", "accountId": acc_id, "name": "Lumen Client LLC", "plan": plan}]
        self.repo.mutate_state({
            "lumen_accounts": json.dumps(accounts),
            "lumen_profiles": json.dumps(profiles),
        })

    def test_strip_account_secrets_removes_team_user_hashes(self) -> None:
        u_salt = "b" * 32
        u_hash = compute_password_hash("TeamPass123", u_salt)
        self._seed_account(
            "acc-1",
            "owner@client.ae",
            plan="advance",
            team_users=[
                {
                    "id": "usr-1",
                    "name": "Sara",
                    "email": "sara@client.ae",
                    "role": "accountant",
                    "status": "active",
                    "salt": u_salt,
                    "passwordHash": u_hash,
                    "resetCodeHash": "secret-reset",
                }
            ],
        )
        scoped = self.repo.get_scoped_state("acc-1")
        accs = json.loads(scoped["lumen_accounts"])
        tu = accs["acc-1"]["teamUsers"][0]
        self.assertEqual(tu["email"], "sara@client.ae")
        self.assertNotIn("passwordHash", tu)
        self.assertNotIn("salt", tu)
        self.assertNotIn("resetCodeHash", tu)

    def test_verify_login_and_password_reset_for_team_user(self) -> None:
        u_salt = "c" * 32
        u_hash = compute_password_hash("TeamPass123", u_salt)
        self._seed_account(
            "acc-2",
            "owner2@client.ae",
            plan="advance",
            team_users=[
                {
                    "id": "usr-2",
                    "name": "Omar",
                    "email": "omar@client.ae",
                    "role": "viewer",
                    "profileIds": ["prof-acc-2"],
                    "status": "active",
                    "salt": u_salt,
                    "passwordHash": u_hash,
                }
            ],
        )

        # Successful team user login
        res = self.repo.verify_login("omar@client.ae", "TeamPass123")
        self.assertTrue(res["ok"])
        self.assertEqual(res["accountId"], "acc-2")
        self.assertIn("sessionToken", res)
        self.assertEqual(res["teamUser"]["id"], "usr-2")
        self.assertEqual(res["teamUser"]["role"], "viewer")
        self.assertEqual(res["teamUser"]["profileIds"], ["prof-acc-2"])

        # 3 failed attempts lock the team user
        for _ in range(3):
            bad = self.repo.verify_login("omar@client.ae", "WrongPass1")
            self.assertFalse(bad["ok"])
        self.assertTrue(bad.get("locked"))

        # Password reset unlocks and updates team user password
        req = self.repo.request_password_reset("omar@client.ae")
        self.assertTrue(req["ok"])
        conf = self.repo.confirm_password_reset("omar@client.ae", req["resetCode"], "NewTeamPass9")
        self.assertTrue(conf["ok"])
        after = self.repo.verify_login("omar@client.ae", "NewTeamPass9")
        self.assertTrue(after["ok"])

    def test_mutate_scoped_state_enforces_plan_user_limits_and_preserves_hashes(self) -> None:
        u_salt = "d" * 32
        u_hash = compute_password_hash("TeamPass123", u_salt)
        self._seed_account(
            "acc-basic",
            "basic@client.ae",
            plan="basic",
            team_users=[
                {
                    "id": "usr-1",
                    "name": "User One",
                    "email": "u1@client.ae",
                    "role": "accountant",
                    "status": "active",
                    "salt": u_salt,
                    "passwordHash": u_hash,
                }
            ],
        )

        # Client tries to update usr-1 role (without sending passwordHash/salt) AND sneak a 2nd team user on Basic plan (max 2 total = 1 primary + 1 team user)
        incoming = {
            "acc-basic": {
                "teamUsers": [
                    {"id": "usr-1", "name": "User One", "email": "u1@client.ae", "role": "viewer", "status": "active"},
                    {"id": "usr-2", "name": "User Two", "email": "u2@client.ae", "role": "viewer", "status": "active", "salt": "e" * 32, "passwordHash": compute_password_hash("Pass1234", "e" * 32)},
                ]
            }
        }
        self.repo.mutate_scoped_state("acc-basic", {"lumen_accounts": json.dumps(incoming)})

        full = self.repo.get_all_state()
        saved_acc = json.loads(full["lumen_accounts"])["acc-basic"]
        # Basic plan cap: only 1 team user (2 total seats including primary)
        self.assertEqual(len(saved_acc["teamUsers"]), 1)
        self.assertEqual(saved_acc["teamUsers"][0]["role"], "viewer")
        # Existing password hash and salt must be preserved!
        self.assertEqual(saved_acc["teamUsers"][0]["passwordHash"], u_hash)
        self.assertEqual(saved_acc["teamUsers"][0]["salt"], u_salt)

    def test_viewer_and_accountant_rbac_and_fail_closed_profile_scope(self) -> None:
        v_salt, a_salt = "f" * 32, "1" * 32
        self._seed_account(
            "acc-rbac",
            "owner-rbac@client.ae",
            plan="advance",
            team_users=[
                {"id": "usr-view", "name": "Viewer", "email": "view@client.ae", "role": "viewer", "status": "active", "salt": v_salt, "passwordHash": compute_password_hash("ViewPass123", v_salt), "profileIds": ["prof-acc-rbac"]},
                {"id": "usr-acct", "name": "Acct", "email": "acct@client.ae", "role": "accountant", "status": "active", "salt": a_salt, "passwordHash": compute_password_hash("AcctPass123", a_salt), "profileIds": ["prof-acc-rbac"]},
            ],
        )
        self.repo.mutate_state({
            "lumen_profiles": json.dumps([
                {"id": "prof-acc-rbac", "accountId": "acc-rbac", "name": "Assigned Co"},
                {"id": "prof-other", "accountId": "acc-rbac", "name": "Other Co"},
            ]),
            "profile:prof-acc-rbac::journal": "[]",
            "profile:prof-other::journal": "[1]",
            PLATFORM_INTEGRATIONS_KEY: json.dumps({"flowiseEndpoint": "https://ai.example"}),
            PLATFORM_SECRETS_KEY: json.dumps({"recaptchaSecretKey": "secret-xyz"}),
        })

        v_login = self.repo.verify_login("view@client.ae", "ViewPass123")
        self.assertTrue(v_login["ok"])
        self.assertEqual((v_login.get("teamUser") or {}).get("role"), "viewer")
        v_ctx = self.repo.resolve_caller_context(account_header="acc-rbac", session_header=str(v_login["sessionToken"]))
        self.assertEqual((v_ctx.account_id, v_ctx.team_user_id, v_ctx.role), ("acc-rbac", "usr-view", "viewer"))

        with self.assertRaises(PermissionError):
            self.repo.mutate_scoped_state("acc-rbac", {"profile:prof-acc-rbac::journal": "[2]"}, caller_context=v_ctx)
        with self.assertRaises(PermissionError):
            self.repo.put_attachments({"prof-acc-rbac::inv-1": "data:text/plain;base64,QQ=="}, account_id="acc-rbac", caller_context=v_ctx)

        acct_ctx = CallerContext("acc-rbac", team_user_id="usr-acct", role="accountant", profile_ids=("prof-acc-rbac",))
        with self.assertRaises(PermissionError):
            self.repo.mutate_scoped_state("acc-rbac", {"lumen_accounts": "{}"}, caller_context=acct_ctx)
        with self.assertRaises(PermissionError):
            self.repo.mutate_scoped_state("acc-rbac", {"lumen_profiles": "[]"}, caller_context=acct_ctx)
        with self.assertRaises(PermissionError):
            self.repo.mutate_scoped_state("acc-rbac", {"profile:prof-other::journal": "[9]"}, caller_context=acct_ctx)

        missing_ctx = CallerContext("acc-rbac", team_user_id="usr-missing", role="accountant", profile_ids=("prof-missing",))
        scoped_missing = self.repo.get_scoped_state("acc-rbac", caller_context=missing_ctx)
        self.assertEqual(json.loads(scoped_missing["lumen_profiles"]), [])
        self.assertNotIn("profile:prof-acc-rbac::journal", scoped_missing)
        self.assertIn(PLATFORM_INTEGRATIONS_KEY, scoped_missing)
        self.assertNotIn(PLATFORM_SECRETS_KEY, scoped_missing)

    def test_auth_captcha_payment_method_and_viewer_403_http(self) -> None:
        self._seed_account(
            "acc-rbac-http",
            "rbac-admin@example.com",
            plan="advance",
            team_users=[
                {"id": "tu-v1", "name": "Read Only", "email": "readonly@example.com", "role": "viewer", "status": "active", "salt": "b" * 32, "passwordHash": compute_password_hash("ViewerPass123", "b" * 32)},
            ],
        )
        server = ThreadingHTTPServer(("127.0.0.1", 0), agy_service.AgyPredictionHandler)
        port = server.server_address[1]
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base_url = f"http://127.0.0.1:{port}"
        headers = {"Origin": base_url, "Content-Type": "application/json", "X-Lumen-Client": "lumen-bookkeeping-web"}
        try:
            with patch.object(agy_service, "ALLOWED_ORIGINS", (base_url, "https://app.example.com")), patch.object(agy_service, "get_state_repo", return_value=self.repo), patch.dict(os.environ, {"RECAPTCHA_SITE_KEY": "site-key-1", "RECAPTCHA_SECRET_KEY": ""}, clear=False):
                with urllib.request.urlopen(urllib.request.Request(f"{base_url}/api/v1/auth/captcha-config", headers=headers, method="GET"), timeout=5) as resp:
                    cap_cfg = json.loads(resp.read().decode("utf-8"))
                    self.assertEqual((resp.status, cap_cfg["ok"], cap_cfg["siteKey"]), (200, True, "site-key-1"))

                non_local_req = urllib.request.Request(
                    f"{base_url}/api/v1/auth/captcha/verify",
                    data=json.dumps({"token": "tok-123"}).encode("utf-8"),
                    headers={"Origin": "https://app.example.com", "Content-Type": "application/json", "X-Lumen-Client": "lumen-bookkeeping-web"},
                    method="POST",
                )
                with self.assertRaises(urllib.error.HTTPError) as cap_ctx:
                    urllib.request.urlopen(non_local_req, timeout=5)
                self.assertEqual(cap_ctx.exception.code, 503)

                with urllib.request.urlopen(urllib.request.Request(f"{base_url}/api/v1/auth/login", data=json.dumps({"email": "readonly@example.com", "password": "ViewerPass123"}).encode("utf-8"), headers=headers, method="POST"), timeout=5) as resp:
                    v_sess = json.loads(resp.read().decode("utf-8"))["sessionToken"]
                viewer_headers = {**headers, "X-Lumen-Account": "acc-rbac-http", "X-Lumen-Session": v_sess}
                for ep, body in (
                    ("/api/v1/state", {"set": {"profile:prof-acc-rbac-http::journal": "[]"}}),
                    ("/api/v1/attachments", {"key": "prof-acc-rbac-http::inv-1", "data": "data:text/plain;base64,QQ=="}),
                    ("/api/v1/auth/payment-method", {"email": "rbac-admin@example.com", "cardLast4": "4242"}),
                ):
                    with self.assertRaises(urllib.error.HTTPError) as err_ctx:
                        urllib.request.urlopen(urllib.request.Request(f"{base_url}{ep}", data=json.dumps(body).encode("utf-8"), headers=viewer_headers, method="POST"), timeout=5)
                    self.assertEqual(err_ctx.exception.code, 403)

                with urllib.request.urlopen(urllib.request.Request(f"{base_url}/api/v1/auth/login", data=json.dumps({"email": "rbac-admin@example.com", "password": "Password123"}).encode("utf-8"), headers=headers, method="POST"), timeout=5) as resp:
                    a_sess = json.loads(resp.read().decode("utf-8"))["sessionToken"]
                admin_headers = {**headers, "X-Lumen-Account": "acc-rbac-http", "X-Lumen-Session": a_sess}
                with urllib.request.urlopen(urllib.request.Request(f"{base_url}/api/v1/auth/payment-method", data=json.dumps({"email": "rbac-admin@example.com", "cardHolderName": "RBAC Co", "cardBrand": "Visa", "cardLast4": "4242", "cardExpiry": "12/28"}).encode("utf-8"), headers=admin_headers, method="POST"), timeout=5) as resp:
                    self.assertEqual((resp.status, json.loads(resp.read().decode("utf-8")).get("ok")), (200, True))
        finally:
            server.shutdown()
            server.server_close()

    def test_bare_x_lumen_account_fails_closed_and_einvoice_enforces_profile_scope(self) -> None:
        salt = "c" * 32
        pw_hash = compute_password_hash("Password123", salt)
        self.repo.mutate_state({
            "lumen_accounts": json.dumps({
                "acc-einv": {
                    "email": "einv-admin@example.com", "companyName": "Einv Co", "plan": "advance", "status": "active",
                    "salt": salt, "passwordHash": pw_hash,
                    "teamUsers": [{"id": "tu-acct", "name": "Scoped Acct", "email": "scoped-einv@example.com", "role": "accountant", "status": "active", "profileIds": ["prof-b"], "salt": salt, "passwordHash": pw_hash}],
                }
            }),
            "lumen_profiles": json.dumps([
                {"id": "prof-a", "accountId": "acc-einv", "name": "Entity A"},
                {"id": "prof-b", "accountId": "acc-einv", "name": "Entity B"},
            ]),
            "profile:prof-a::bookkeeping_history_v2": '[{"id":"inv-a","invoiceNum":"INV-A"}]',
            "profile:prof-b::bookkeeping_history_v2": '[{"id":"inv-b","invoiceNum":"INV-B"}]',
            PLATFORM_SECRETS_KEY: '{"smtpPass":"secret-123"}',
        })
        server = ThreadingHTTPServer(("127.0.0.1", 0), agy_service.AgyPredictionHandler)
        port = server.server_address[1]
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base_url = f"http://127.0.0.1:{port}"
        headers = {"Origin": base_url, "Content-Type": "application/json", "X-Lumen-Client": "lumen-bookkeeping-web"}
        try:
            with patch.object(agy_service, "ALLOWED_ORIGINS", (base_url,)), patch.object(agy_service, "get_state_repo", return_value=self.repo), patch.object(agy_service, "run_agy_prediction", return_value={"text": "OK"}) as mock_ai:
                bare_owner = {**headers, "X-Lumen-Account": "owner"}
                with urllib.request.urlopen(urllib.request.Request(f"{base_url}/api/v1/auth/session", headers=bare_owner, method="GET"), timeout=5) as resp:
                    sess_data = json.loads(resp.read().decode("utf-8"))
                    self.assertEqual((sess_data["authenticated"], "sessionToken" in sess_data), (False, False))
                with urllib.request.urlopen(urllib.request.Request(f"{base_url}/api/v1/state", headers=bare_owner, method="GET"), timeout=5) as resp:
                    bare_state = json.loads(resp.read().decode("utf-8"))["state"]
                    self.assertNotIn(PLATFORM_SECRETS_KEY, bare_state)
                    self.assertNotIn("profile:prof-a::bookkeeping_history_v2", bare_state)
                    self.assertEqual(bare_state["lumen_profiles"], "[]")
                with urllib.request.urlopen(urllib.request.Request(f"{base_url}/api/v1/state", data=json.dumps({"set": {"profile:prof-a::bookkeeping_history_v2": "[]"}}).encode("utf-8"), headers=bare_owner, method="POST"), timeout=5) as resp:
                    self.assertEqual(json.loads(resp.read().decode("utf-8"))["updated"], 0)
                with self.assertRaises(urllib.error.HTTPError) as pm_ctx:
                    urllib.request.urlopen(urllib.request.Request(f"{base_url}/api/v1/auth/payment-method", data=json.dumps({"email": "einv-admin@example.com", "cardHolderName": "X", "cardLast4": "4242", "cardExpiry": "12/28"}).encode("utf-8"), headers={**headers, "X-Lumen-Account": "acc-einv"}, method="POST"), timeout=5)
                self.assertEqual(pm_ctx.exception.code, 403)

                reg_payload = {"set": {"lumen_accounts": json.dumps({"acc-new": {"email": "new-tenant@example.com", "plan": "advance", "salt": salt, "passwordHash": pw_hash}})}}
                with urllib.request.urlopen(urllib.request.Request(f"{base_url}/api/v1/state", data=json.dumps(reg_payload).encode("utf-8"), headers=headers, method="POST"), timeout=5) as resp:
                    self.assertEqual(json.loads(resp.read().decode("utf-8"))["updated"], 1)
                new_acc = json.loads(self.repo.get_all_state()["lumen_accounts"])["acc-new"]
                self.assertEqual((new_acc["plan"], new_acc["requestedPlan"], new_acc["aiAddon"]), ("basic", "advance", False))
                with urllib.request.urlopen(urllib.request.Request(f"{base_url}/api/v1/state", data=json.dumps({"set": {"lumen_accounts": json.dumps({"acc-dup": {"email": "new-tenant@example.com", "salt": salt, "passwordHash": pw_hash}})}}).encode("utf-8"), headers=headers, method="POST"), timeout=5) as resp:
                    self.assertEqual(json.loads(resp.read().decode("utf-8"))["updated"], 0)

                with urllib.request.urlopen(urllib.request.Request(f"{base_url}/api/v1/auth/login", data=json.dumps({"email": "scoped-einv@example.com", "password": "Password123"}).encode("utf-8"), headers=headers, method="POST"), timeout=5) as resp:
                    acct_tok = json.loads(resp.read().decode("utf-8"))["sessionToken"]
                acct_headers = {**headers, "X-Lumen-Account": "acc-einv", "X-Lumen-Session": acct_tok}
                with self.assertRaises(urllib.error.HTTPError) as dead_auth_ctx:
                    urllib.request.urlopen(urllib.request.Request(f"{base_url}/api/v1/auth/sms-otp/send", data=b"{}", headers=acct_headers, method="POST"), timeout=5)
                self.assertEqual(dead_auth_ctx.exception.code, 404)
                self.assertEqual(mock_ai.call_count, 0)

                xml = "<Invoice><cbc:CustomizationID>urn:peppol:pint:billing-1@ae-1</cbc:CustomizationID></Invoice>"
                for ep in ("/api/v1/einvoice/submit", "/api/v1/einvoice/inbound"):
                    with self.assertRaises(urllib.error.HTTPError) as einv_ctx:
                        urllib.request.urlopen(urllib.request.Request(f"{base_url}{ep}", data=json.dumps({"profileId": "prof-a", "invoiceId": "inv-a", "xml": xml}).encode("utf-8"), headers=acct_headers, method="POST"), timeout=5)
                    self.assertEqual(einv_ctx.exception.code, 403)
                with urllib.request.urlopen(urllib.request.Request(f"{base_url}/api/v1/einvoice/submit", data=json.dumps({"profileId": "prof-b", "invoiceId": "inv-b", "xml": xml}).encode("utf-8"), headers=acct_headers, method="POST"), timeout=5) as resp:
                    self.assertEqual((resp.status, json.loads(resp.read().decode("utf-8")).get("ok")), (200, True))

                # Fail-closed prediction when X-Lumen-Account/Session omitted or unauthenticated
                for bad_ai_hdrs in (headers, bare_owner):
                    with self.assertRaises(urllib.error.HTTPError) as ai_ctx:
                        urllib.request.urlopen(urllib.request.Request(f"{base_url}/api/v1/prediction/test", data=b"{}", headers=bad_ai_hdrs, method="POST"), timeout=5)
                    self.assertEqual(ai_ctx.exception.code, 403)
                self.assertEqual(mock_ai.call_count, 0)

                # HMAC delimiter collision (`owner:pwn`) & self-registration billing strip + captcha requirement
                with urllib.request.urlopen(urllib.request.Request(f"{base_url}/api/v1/state", data=json.dumps({"set": {"lumen_accounts": json.dumps({"owner:pwn": {"email": "pwn@evil.ae", "salt": salt, "passwordHash": pw_hash}})}}).encode("utf-8"), headers=headers, method="POST"), timeout=5) as resp:
                    self.assertEqual(json.loads(resp.read().decode("utf-8"))["updated"], 0)
                with self.assertRaises(ValueError):
                    self.repo.issue_session_token("owner:pwn")
                forged = f"sess.owner.pwn.{'0' * 24}.{'0' * 64}"
                self.assertEqual(self.repo.resolve_caller_context(account_header="owner", session_header=forged).role, "unauthenticated")

                # Self-reg strips billing fields & requires captcha when RECAPTCHA_SECRET_KEY is configured
                with urllib.request.urlopen(urllib.request.Request(f"{base_url}/api/v1/state", data=json.dumps({"set": {"lumen_accounts": json.dumps({"acc-strip": {"email": "strip@example.com", "lastChargedAt": "2026-01-01T00:00:00Z", "lastChargedAmount": 999, "salt": salt, "passwordHash": pw_hash}})}}).encode("utf-8"), headers=headers, method="POST"), timeout=5) as resp:
                    self.assertEqual(json.loads(resp.read().decode("utf-8"))["updated"], 1)
                self.assertNotIn("lastChargedAt", json.loads(self.repo.get_all_state()["lumen_accounts"])["acc-strip"])
                with patch.dict(os.environ, {"RECAPTCHA_SECRET_KEY": "sec-cap"}):
                    with self.assertRaises(urllib.error.HTTPError) as cap_reg_ctx:
                        urllib.request.urlopen(urllib.request.Request(f"{base_url}/api/v1/state", data=json.dumps({"set": {"lumen_accounts": json.dumps({"acc-capfail": {"email": "capfail@example.com", "salt": salt, "passwordHash": pw_hash}})}}).encode("utf-8"), headers=headers, method="POST"), timeout=5)
                    self.assertEqual(cap_reg_ctx.exception.code, 403)
        finally:
            server.shutdown()
            server.server_close()

        # Cross-tenant teamUsers email collision rejected even when caller owns target account
        existing_accs = json.loads(self.repo.get_all_state()["lumen_accounts"])
        blocked = collect_reserved_emails(existing_accs, exclude_acc_id="acc-new", own_email="new-tenant@example.com")
        self.assertEqual(merge_team_users([], [{"id": "tu-col", "email": "einv-admin@example.com", "salt": salt, "passwordHash": pw_hash}], "premium", is_owner=True, blocked_emails=blocked), [])

        # Primary tenant admin cannot mutate login email via /api/v1/state; deleted account's signed token fails closed and cannot resurrect itself
        self.repo.mutate_scoped_state("acc-einv", {"lumen_accounts": json.dumps({"acc-einv": {"email": "strip@example.com"}})}, caller_context=CallerContext("acc-einv", role="admin"))
        self.assertEqual(json.loads(self.repo.get_all_state()["lumen_accounts"])["acc-einv"]["email"], "einv-admin@example.com")
        del_tok = self.repo.issue_session_token("acc-strip")
        accs_after = json.loads(self.repo.get_all_state()["lumen_accounts"])
        accs_after.pop("acc-strip", None)
        self.repo.mutate_state({"lumen_accounts": json.dumps(accs_after)})
        self.assertEqual(self.repo.resolve_caller_context(account_header="acc-strip", session_header=del_tok).role, "unauthenticated")
        self.assertFalse(self.repo.resolve_session(account_header="acc-strip", session_header=del_tok)["authenticated"])
        self.assertEqual(self.repo.mutate_scoped_state("acc-strip", {"lumen_accounts": json.dumps({"acc-strip": {"email": "einv-admin@example.com", "salt": salt, "passwordHash": pw_hash, "lastChargedAt": "2026-01-01T00:00:00Z"}})}, caller_context=self.repo.resolve_caller_context(account_header="acc-strip", session_header=del_tok)), 0)
        self.assertNotIn("acc-strip", json.loads(self.repo.get_all_state()["lumen_accounts"]))

    def test_support_server_rejects_unknown_post_and_enforces_einvoice_rbac(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), support_server.BookkeepingRequestHandler)
        port = server.server_address[1]
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base_url = f"http://127.0.0.1:{port}"
        try:
            with patch.object(agy_service, "get_state_repo", return_value=self.repo):
                for dead_path in ("/api/v1/unknown-route", "/api/v1/auth/sms-otp/send", "/api/v1/einvoice/submit"):
                    with self.assertRaises(urllib.error.HTTPError) as err_ctx:
                        urllib.request.urlopen(urllib.request.Request(f"{base_url}{dead_path}", data=b"{}", headers={"Content-Type": "application/json"}, method="POST"), timeout=5)
                    self.assertEqual(err_ctx.exception.code, 403 if dead_path.endswith("submit") else 404)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
