"""Unit and integration tests for `/welcome` entrypoint, registration, login, and profile scoping."""

from __future__ import annotations

from pathlib import Path
import re
import unittest
import urllib.request

from features.support_server import BookkeepingRequestHandler, ThreadingHTTPServer

REPO_ROOT = Path(__file__).resolve().parent.parent
APP_DIR = REPO_ROOT.parent / "bookkeeping-tool"


class WelcomeEntrypointAndAuthUnitTests(unittest.TestCase):
    """Verify `/welcome` entrypoint guard, registration, login, and sign-out contracts."""

    def test_profiles_storage_requires_explicit_authentication_and_redirects_unauthenticated_root_to_welcome(self) -> None:
        profiles_js = (APP_DIR / "profiles-storage.js").read_text(encoding="utf-8")

        # Must expose isAuthenticated() and resolveWelcomeUrl()
        self.assertIn("isAuthenticated", profiles_js)
        self.assertIn("resolveWelcomeUrl", profiles_js)

        # Must NOT unconditionally fall back to OWNER_ACCOUNT when CURRENT_ACCOUNT_KEY is absent
        self.assertNotIn(
            "const currentAccountId = () => raw.get.call(store, CURRENT_ACCOUNT_KEY) || OWNER_ACCOUNT;",
            profiles_js,
        )

        # Must redirect unauthenticated visitors on non-welcome pages to /welcome
        self.assertIn("window.location.replace", profiles_js)
        self.assertIn("/welcome", profiles_js)

        # Must compute active profile prefix dynamically rather than caching once at script load
        self.assertNotIn("const activePrefix = prefixFor(getActiveId());", profiles_js)
        self.assertIn("getActivePrefix", profiles_js)

    def test_auth_js_provides_sha256_fallback_signin_validation_and_registration_helper(self) -> None:
        auth_js = (APP_DIR / "auth.js").read_text(encoding="utf-8")

        # Must support non-SecureContext environments where crypto.subtle is undefined
        self.assertIn("sha256Fallback", auth_js)
        self.assertIn("validateSignIn", auth_js)
        self.assertIn("register", auth_js)

        # Must normalize email before validating or looking up accounts
        self.assertIn(".trim().toLowerCase()", auth_js)

    def test_welcome_html_and_js_expose_entrypoint_controls_for_guest_and_authenticated_users(self) -> None:
        welcome_html = (APP_DIR / "welcome.html").read_text(encoding="utf-8")
        welcome_js = (APP_DIR / "welcome.js").read_text(encoding="utf-8")

        # Entrypoint brand link and guest/authenticated topbar actions
        self.assertIn('href="/welcome"', welcome_html)
        self.assertIn('id="btnOpenRegister"', welcome_html)
        self.assertIn('id="btnOpenSignIn"', welcome_html)
        self.assertIn('id="btnOpenBooks"', welcome_html)
        self.assertIn('id="btnWelcomeSignOut"', welcome_html)

        # Setup modal must include plan selector and link to switch to sign-in
        self.assertIn('id="setupPlanSelect"', welcome_html)
        self.assertIn('id="linkSwitchToSignIn"', welcome_html)

        # Welcome JS must wire guest/authenticated state and both modals
        self.assertIn("btnOpenRegister", welcome_js)
        self.assertIn("linkSwitchToSignIn", welcome_js)
        self.assertIn("setupPlanSelect", welcome_js)
        self.assertIn("isAuthenticated", welcome_js)

    def test_topbar_and_settings_render_authenticated_user_identity_and_signout(self) -> None:
        profiles_ui = (APP_DIR / "profiles-ui.js").read_text(encoding="utf-8")
        plan_gating = (APP_DIR / "plan-gating.js").read_text(encoding="utf-8")
        index_html = (APP_DIR / "index.html").read_text(encoding="utf-8")

        # index.html must load auth.js and profiles-storage.js
        self.assertIn("profiles-storage.js", index_html)
        self.assertIn("auth.js", index_html)

        # profiles-ui.js must update topbar .user-profile with current user email/name and sign-out button
        self.assertIn("btnTopbarSignOut", profiles_ui)
        self.assertIn("renderUserProfile", profiles_ui)

        # plan-gating.js must link to /welcome#plans and always provide Sign out
        self.assertIn("/welcome#plans", plan_gating)
        self.assertIn("/welcome", plan_gating)

    def test_support_server_and_nginx_conf_serve_clean_welcome_route(self) -> None:
        nginx_conf = (REPO_ROOT / "default.conf").read_text(encoding="utf-8")
        self.assertIn("try_files $uri $uri.html $uri/ =404;", nginx_conf)

        server = ThreadingHTTPServer(("127.0.0.1", 0), BookkeepingRequestHandler)
        port = server.server_address[1]
        import threading

        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/welcome", timeout=5) as resp:
                self.assertEqual(resp.status, 200)
                body = resp.read().decode("utf-8")
                self.assertIn("Welcome to", body)
                self.assertIn("Lumen Books", body)
                self.assertIn("/__vendor__/fonts.css", body)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
