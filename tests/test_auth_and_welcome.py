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

    def test_bilingual_en_ar_toggle_and_rtl_support_across_welcome_and_books_app(self) -> None:
        profiles_js = (APP_DIR / "profiles-storage.js").read_text(encoding="utf-8")
        welcome_html = (APP_DIR / "welcome.html").read_text(encoding="utf-8")
        index_html = (APP_DIR / "index.html").read_text(encoding="utf-8")
        i18n_js_path = APP_DIR / "i18n.js"
        i18n_css_path = APP_DIR / "i18n.css"

        # 1. Global storage key for language preference across welcome & books app
        self.assertIn("lumen_lang", profiles_js)

        # 2. i18n assets must exist and be wired into welcome.html and index.html
        self.assertTrue(i18n_js_path.is_file(), "i18n.js must exist in bookkeeping-tool")
        self.assertTrue(i18n_css_path.is_file(), "i18n.css must exist in bookkeeping-tool")
        self.assertIn("i18n.js", welcome_html)
        self.assertIn("i18n.css", welcome_html)
        self.assertIn("i18n.js", index_html)
        self.assertIn("i18n.css", index_html)

        # 3. Topbar language switcher button in both pages
        self.assertIn('id="btnLangToggle"', welcome_html)
        self.assertIn('id="btnLangToggle"', index_html)

        # 4. i18n.js must expose LumenI18n API, RTL dir switching, and Arabic translations
        i18n_js = i18n_js_path.read_text(encoding="utf-8")
        self.assertIn("LumenI18n", i18n_js)
        self.assertIn("setLang", i18n_js)
        self.assertIn("toggleLang", i18n_js)
        self.assertIn("document.documentElement.dir", i18n_js)
        self.assertIn("لوحة التحكم", i18n_js)
        self.assertIn("مرحباً بك في", i18n_js)

        # 5. i18n.css must define RTL layout rules for both welcome and main app
        i18n_css = i18n_css_path.read_text(encoding="utf-8")
        self.assertIn('[dir="rtl"]', i18n_css)


class BehavioralAuthTenantAndEdgeProxyTests(unittest.TestCase):
    """Execute `plan-access.js`, `profiles-storage.js`, `auth.js`, and `functions/api/[[path]].js` in Node.js."""

    def test_multi_tenant_isolation_privilege_escalation_guards_and_edge_proxy_in_node(self) -> None:
        import json
        import subprocess

        node_script = r"""
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const appDir = process.env.APP_DIR;

// 1. Setup simulated browser Storage & DOM
const backing = new Map();
class FakeStorage {
    getItem(k) { return backing.has(k) ? backing.get(k) : null; }
    setItem(k, v) { backing.set(k, String(v)); }
    removeItem(k) { backing.delete(k); }
    key(i) { return Array.from(backing.keys())[i] || null; }
    get length() { return backing.size; }
}
const store = new FakeStorage();
global.Storage = FakeStorage;
global.localStorage = store;
global.window = {
    localStorage: store,
    location: { pathname: '/welcome', search: '', href: '/welcome', replace: (u) => { global.window.location.href = u; } },
    dispatchEvent: () => {}
};
global.CustomEvent = class CustomEvent { constructor(name, opts) { this.name = name; this.detail = opts && opts.detail; } };

const planAccess = require(path.join(appDir, 'plan-access.js'));
assert.strictEqual(planAccess.normalizePlan('free'), 'basic');
assert.strictEqual(planAccess.normalizePlan('trial'), 'basic');
assert.strictEqual(planAccess.normalizePlan('pro'), 'advance');
assert.strictEqual(planAccess.normalizePlan('enterprise'), 'premium');

const Profiles = require(path.join(appDir, 'profiles-storage.js'));
const Auth = require(path.join(appDir, 'auth.js'));

// Unauthenticated visitor must NOT get owner profile or owner data
assert.strictEqual(Profiles.isAuthenticated(), false);
store.setItem('bookkeeping_history_v2', JSON.stringify([{ id: 'unauth-leak' }]));
assert(backing.has('profile:unauthenticated::bookkeeping_history_v2'));
assert(!backing.has('bookkeeping_history_v2'));

(async () => {
    // Register a non-owner tenant account
    const reg = await Auth.register({
        email: 'Tenant1@Example.com',
        companyName: 'Tenant One LLC',
        planId: 'basic',
        password: 'StrongPassword!123'
    });
    assert.strictEqual(reg.ok, true);
    assert.strictEqual(Profiles.isAuthenticated(), true);
    assert.strictEqual(Profiles.isOwner(), false);
    assert.strictEqual(Profiles.getPlan(), 'basic');

    // Non-owner must NOT be able to escalate plan via setPlan()
    const escalated = Profiles.setPlan('premium');
    assert.strictEqual(escalated, false);
    assert.strictEqual(Profiles.getPlan(), 'basic');

    // Non-owner must NOT be able to call owner-only admin functions
    assert.deepStrictEqual(Profiles.listAllAccounts(), []);
    assert.strictEqual(Profiles.updateAccountAdmin(reg.accountId, { plan: 'premium' }), false);
    assert.strictEqual(Profiles.approvePlanRequest(reg.accountId, 'advance'), false);
    assert.strictEqual(Profiles.impersonateAccount('owner'), false);

    // Non-owner tenant data is isolated under its own profile prefix
    store.setItem('bookkeeping_history_v2', JSON.stringify([{ id: 'tenant-1-inv' }]));
    assert.strictEqual(backing.has('bookkeeping_history_v2'), false);

    // Validate sign-in password verification
    const badLogin = await Auth.signIn('tenant1@example.com', 'WrongPass');
    assert.strictEqual(badLogin, false);
    const goodLogin = await Auth.signIn('  TENANT1@example.com ', 'StrongPassword!123');
    assert.strictEqual(goodLogin, true);

    // Owner sign-in can mutate plan & approve requests
    Profiles.requestPlanUpgrade('advance', 'monthly');
    const adminSignedIn = await Auth.signInAdmin('admin@lumenconsultancy.net', 'LumenAdmin2026');
    assert.strictEqual(adminSignedIn, true);
    assert.strictEqual(Profiles.isOwner(), true);
    assert.strictEqual(Profiles.listAllAccounts().length >= 1, true);
    const approved = Profiles.approvePlanRequest(reg.accountId, 'advance');
    assert.strictEqual(approved, true);
    const updatedTenant = Profiles.findAccountByEmail('tenant1@example.com');
    assert.strictEqual(updatedTenant.plan, 'advance');

    // 2. Test Cloudflare Pages Edge Function (functions/api/[[path]].js)
    const edgeSrc = fs.readFileSync(path.join(appDir, 'functions', 'api', '[[path]].js'), 'utf8')
        .replace(/export\s+async\s+function\s+onRequest/g, 'async function onRequest')
        + '\nmodule.exports = { onRequest };';
    const edgeMod = { exports: {} };
    let lastFetched = null;
    let shouldThrowFetch = false;
    const edgeSandbox = {
        module: edgeMod,
        exports: edgeMod.exports,
        URL,
        Headers,
        Response,
        fetch: async (url, init) => {
            if (shouldThrowFetch) throw new Error('ECONNREFUSED');
            lastFetched = { url, init };
            return new Response(JSON.stringify({ text: 'ok' }), {
                status: 200,
                headers: { 'Content-Type': 'application/json' }
            });
        }
    };
    vm.runInNewContext(edgeSrc, edgeSandbox);
    const { onRequest } = edgeMod.exports;

    // 405 on DELETE
    const res405 = await onRequest({
        request: new Request('https://lumen-bookkeeping.pages.dev/api/v1/prediction/1', { method: 'DELETE' }),
        env: { AGY_BACKEND_URL: 'https://backend.example.com' }
    });
    assert.strictEqual(res405.status, 405);

    // 401 on GET without X-Lumen-Client
    const res401Get = await onRequest({
        request: new Request('https://lumen-bookkeeping.pages.dev/api/v1/ping', { method: 'GET' }),
        env: { AGY_BACKEND_URL: 'https://backend.example.com' }
    });
    assert.strictEqual(res401Get.status, 401);

    // 403 on untrusted Origin
    const res403 = await onRequest({
        request: new Request('https://lumen-bookkeeping.pages.dev/api/v1/prediction/1', {
            method: 'POST',
            headers: { 'X-Lumen-Client': 'lumen-bookkeeping-web', 'Origin': 'https://evil.example.com' },
            body: '{}'
        }),
        env: { AGY_BACKEND_URL: 'https://backend.example.com' }
    });
    assert.strictEqual(res403.status, 403);

    // 503 when AGY_BACKEND_URL is not configured (fail closed, no plain-HTTP EC2 fallback)
    const res503 = await onRequest({
        request: new Request('https://lumen-bookkeeping.pages.dev/api/v1/prediction/1', {
            method: 'POST',
            headers: { 'X-Lumen-Client': 'lumen-bookkeeping-web', 'Origin': 'https://lumen-bookkeeping.pages.dev' },
            body: '{}'
        }),
        env: {}
    });
    assert.strictEqual(res503.status, 503);

    // 502 when upstream fetch throws
    shouldThrowFetch = true;
    const res502 = await onRequest({
        request: new Request('https://lumen-bookkeeping.pages.dev/api/v1/prediction/1', {
            method: 'POST',
            headers: { 'X-Lumen-Client': 'lumen-bookkeeping-web', 'Origin': 'https://lumen-bookkeeping.pages.dev' },
            body: '{}'
        }),
        env: { AGY_BACKEND_URL: 'https://backend.example.com', AGY_API_SECRET: 'sec-123' }
    });
    assert.strictEqual(res502.status, 502);

    // 200 when valid and injects X-Agy-Proxy-Secret
    shouldThrowFetch = false;
    const res200 = await onRequest({
        request: new Request('https://lumen-bookkeeping.pages.dev/api/v1/prediction/1', {
            method: 'POST',
            headers: { 'X-Lumen-Client': 'lumen-bookkeeping-web', 'Origin': 'https://lumen-bookkeeping.pages.dev' },
            body: '{"question":"hi"}'
        }),
        env: { AGY_BACKEND_URL: 'https://backend.example.com', AGY_API_SECRET: 'sec-123' }
    });
    assert.strictEqual(res200.status, 200);
    assert.strictEqual(lastFetched.init.headers.get('X-Agy-Proxy-Secret'), 'sec-123');

    // 3. Test plan-gating.js canOpen enforcement for basic vs advance/premium screens
    await Auth.signIn('tenant1@example.com', 'StrongPassword!123');
    Profiles.updateAccountAdmin(reg.accountId, { plan: 'basic' });
    await Auth.signInAdmin('admin@lumenconsultancy.net', 'LumenAdmin2026');
    Profiles.updateAccountAdmin(reg.accountId, { plan: 'basic' });
    await Auth.signIn('tenant1@example.com', 'StrongPassword!123');
    assert.strictEqual(Profiles.getPlan(), 'basic');
    const PlanGate = require(path.join(appDir, 'plan-gating.js'));
    assert.strictEqual(PlanGate.canOpen('view-dashboard'), true);
    assert.strictEqual(PlanGate.canOpen('view-audit'), false);
    assert.strictEqual(PlanGate.canOpen('view-equity-statement'), false);
    assert.strictEqual(PlanGate.canOpen('view-tax'), false);

    console.log(JSON.stringify({ status: 'ok' }));
})().catch((err) => {
    console.error(err);
    process.exit(1);
});
"""
        proc = subprocess.run(
            ["node", "-e", node_script],
            env={"PATH": "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin", "APP_DIR": str(APP_DIR)},
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout.strip().splitlines()[-1])
        self.assertEqual(payload["status"], "ok")

        # 4. Verify switchView in script.js enforces .app-view validation & LumenPlanGate.canOpen, and docs parity
        script_js = "\n".join(
            [
                (APP_DIR / "script.js").read_text(encoding="utf-8"),
                *(p.read_text(encoding="utf-8") for p in sorted(APP_DIR.glob("app-*.js"))),
            ]
        )
        self.assertIn("targetEl.classList.contains('app-view')", script_js)
        self.assertIn("window.LumenPlanGate.canOpen(targetId)", script_js)

        for doc_rel in ("docs/product/prd-product-requirements.md", "docs/product/user-guide-and-release-notes.md"):
            doc_text = (REPO_ROOT / doc_rel).read_text(encoding="utf-8")
            self.assertIn("Corporate Tax Only (0% VAT)", doc_text)
            self.assertIn("PBKDF2-SHA256 (120,000 iterations)", doc_text)

        # 5. Verify professional UX design tokens, collapsible sidebar, and Quick-Jump Command Palette
        style_bundle = "\n".join(
            (APP_DIR / name).read_text(encoding="utf-8")
            for name in ("style.css", "components.css", "theme-pro.css", "welcome.css", "admin.css")
        )
        for token in ("--color-surface-canvas", "--color-surface-elevated", "--color-border-focus", "tabular-nums"):
            self.assertIn(token, style_bundle)
        html_bundle = "\n".join(
            [(APP_DIR / "index.html").read_text(encoding="utf-8"), *(p.read_text(encoding="utf-8") for p in sorted(APP_DIR.glob("views-*.js")))]
        )
        for ux_id in ("btnSidebarToggle", "btnQuickJump", "quickJumpModal", "quickJumpInput", "quickJumpList"):
            self.assertIn(ux_id, html_bundle)
        self.assertIn("sidebar-collapsed", script_js)


if __name__ == "__main__":
    unittest.main()
