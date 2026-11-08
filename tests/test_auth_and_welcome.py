"""Unit and integration tests for `/welcome` entrypoint, registration, login, and profile scoping."""

from __future__ import annotations

import json
from pathlib import Path
import threading
import unittest
import urllib.request

import agy_service
from features.support_server import BookkeepingRequestHandler, ThreadingHTTPServer
from tests.js_runner import run_node_script

REPO_ROOT = Path(__file__).resolve().parent.parent
APP_DIR = REPO_ROOT.parent / "bookkeeping-tool"


class WelcomeEntrypointAndAuthUnitTests(unittest.TestCase):
    """Verify `/welcome` entrypoint guard, registration, login, and sign-out contracts."""

    def test_profiles_storage_requires_explicit_authentication_and_redirects_unauthenticated_root_to_welcome(self) -> None:
        profiles_js = (APP_DIR / "profiles-storage.js").read_text(encoding="utf-8")
        for token in (
            "isAuthenticated",
            "resolveWelcomeUrl",
            "window.location.replace",
            "/welcome",
            "getActivePrefix",
            "LOCAL_CONFIG_KEYS",
            "isLocalConfigKey",
            "/api/v1/state",
            "syncFromServer",
        ):
            self.assertIn(token, profiles_js)
        self.assertNotIn("const currentAccountId = () => raw.get.call(store, CURRENT_ACCOUNT_KEY) || OWNER_ACCOUNT;", profiles_js)
        self.assertNotIn("const activePrefix = prefixFor(getActiveId());", profiles_js)
        self.assertIn("/api/v1/attachments", (APP_DIR / "attachments-store.js").read_text(encoding="utf-8"))

    def test_auth_js_provides_sha256_fallback_signin_validation_and_registration_helper(self) -> None:
        auth_js = (APP_DIR / "auth.js").read_text(encoding="utf-8")
        for token in (
            "sha256Fallback",
            "PBKDF2_ITERATIONS",
            "120000",
            "pbkdf2_sha256$",
            "validateSignIn",
            "register",
            "signInWithCloudflareAccess",
            ".trim().toLowerCase()",
        ):
            self.assertIn(token, auth_js)
        self.assertNotIn("LumenAdmin2026", auth_js, "Plaintext default admin password must not appear in auth.js")

    def test_welcome_html_and_js_expose_entrypoint_controls_for_guest_and_authenticated_users(self) -> None:
        welcome_html = (APP_DIR / "welcome.html").read_text(encoding="utf-8")
        welcome_js = (APP_DIR / "welcome.js").read_text(encoding="utf-8")
        for html_token in (
            'href="/welcome"',
            'id="btnOpenRegister"',
            'id="btnOpenSignIn"',
            'id="btnOpenBooks"',
            'id="btnWelcomeSignOut"',
            'id="setupPlanSelect"',
            'id="linkSwitchToSignIn"',
        ):
            self.assertIn(html_token, welcome_html)
        for js_token in ("btnOpenRegister", "linkSwitchToSignIn", "setupPlanSelect", "isAuthenticated"):
            self.assertIn(js_token, welcome_js)

    def test_topbar_and_settings_render_authenticated_user_identity_and_signout(self) -> None:
        profiles_ui = (APP_DIR / "profiles-ui.js").read_text(encoding="utf-8")
        plan_gating = (APP_DIR / "plan-gating.js").read_text(encoding="utf-8")
        index_html = (APP_DIR / "index.html").read_text(encoding="utf-8")
        self.assertIn("profiles-storage.js", index_html)
        self.assertIn("auth.js", index_html)
        self.assertIn("btnTopbarSignOut", profiles_ui)
        self.assertIn("renderUserProfile", profiles_ui)
        self.assertIn("/welcome#plans", plan_gating)
        self.assertIn("/welcome", plan_gating)

    def test_support_server_and_nginx_conf_serve_clean_welcome_route(self) -> None:
        self.assertIn("try_files $uri $uri.html $uri/ =404;", (REPO_ROOT / "default.conf").read_text(encoding="utf-8"))
        server = ThreadingHTTPServer(("127.0.0.1", 0), BookkeepingRequestHandler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/welcome", timeout=5) as resp:
                self.assertEqual(resp.status, 200)
                body = resp.read().decode("utf-8")
                for expected in ("Welcome to", "Lumen Books", "/__vendor__/fonts.css"):
                    self.assertIn(expected, body)
        finally:
            server.shutdown()
            server.server_close()

    def test_bilingual_en_ar_toggle_and_rtl_support_across_welcome_and_books_app(self) -> None:
        welcome_html = (APP_DIR / "welcome.html").read_text(encoding="utf-8")
        index_html = (APP_DIR / "index.html").read_text(encoding="utf-8")
        i18n_js_path = APP_DIR / "i18n.js"
        i18n_css_path = APP_DIR / "i18n.css"
        self.assertIn("lumen_lang", (APP_DIR / "profiles-storage.js").read_text(encoding="utf-8"))
        self.assertTrue(i18n_js_path.is_file() and i18n_css_path.is_file())
        for page_html in (welcome_html, index_html):
            for tok in ("i18n.js", "i18n.css", 'id="btnLangToggle"'):
                self.assertIn(tok, page_html)
        i18n_js = i18n_js_path.read_text(encoding="utf-8")
        for token in ("LumenI18n", "setLang", "toggleLang", "document.documentElement.dir", "لوحة التحكم", "مرحباً بك في"):
            self.assertIn(token, i18n_js)
        self.assertIn('[dir="rtl"]', i18n_css_path.read_text(encoding="utf-8"))

    def test_enterprise_ux_palette_layout_monograms_and_docs_gallery(self) -> None:
        css_files = ("style.css", "components.css", "theme-pro.css", "welcome.css", "profiles.css", "i18n.css", "admin.css")
        style_bundle = "\n".join((APP_DIR / name).read_text(encoding="utf-8") for name in css_files)
        for token in (
            "--color-surface-canvas",
            "--color-surface-elevated",
            "--color-border-focus",
            "--text-color",
            "--primary-color",
            "--hover-color",
            "--danger-color",
            "#0c1a2e",
            "#1d4ed8",
            ".two-col-layout",
            ".data-grid",
            ".editable-grid",
            ".form-summary-box",
            ".financial-summary",
            "content: attr(data-abbr)",
        ):
            self.assertIn(token, style_bundle)
        for legacy_color in ("#8b5cf6", "#a855f7", "#6366f1", "#4f46e5", "#e0e7ff", "#ede9fe"):
            self.assertNotIn(legacy_color, style_bundle.lower())

        router_js = (APP_DIR / "app-core-and-router.js").read_text(encoding="utf-8")
        self.assertIn("item.dataset.abbr", router_js)
        self.assertIn("item.closest('.nav-dropdown-content')", router_js)
        index_html = (APP_DIR / "index.html").read_text(encoding="utf-8")
        self.assertIn('<span class="kbd-hint">Ctrl K</span>', index_html)
        self.assertNotIn("⌘", index_html)
        for chart_token in ("parent.clientWidth", "#067647", "#b42318"):
            self.assertIn(chart_token, agy_service.CHART_JS_SHIM)

        ux_doc = (REPO_ROOT / "docs" / "UX_STYLE_IMPROVEMENTS.md").read_text(encoding="utf-8")
        self.assertIn("docs/UX_STYLE_IMPROVEMENTS.md", (REPO_ROOT / "README.md").read_text(encoding="utf-8"))
        self.assertIn("item.dataset.abbr", (REPO_ROOT / "docs" / "technical" / "architecture-and-execution-flow.md").read_text(encoding="utf-8"))
        self.assertIn("data-abbr", (REPO_ROOT / "docs" / "technical" / "sdd-system-design.md").read_text(encoding="utf-8"))
        self.assertIn("Enterprise Finance Navy", (REPO_ROOT / "docs" / "product" / "user-guide-and-release-notes.md").read_text(encoding="utf-8"))
        self.assertNotIn("bookkeeping-tool", ux_doc)
        next_dir = REPO_ROOT / "docs" / "screenshots" / "ux_improvements" / "next"
        self.assertNotEqual((next_dir / "07_after_credit_notes.png").read_bytes(), (next_dir / "07b_after_credit_notes_card.png").read_bytes())
        for sub in ("initial", "next", "round2/before", "round2/after"):
            for png in sorted((REPO_ROOT / "docs" / "screenshots" / "ux_improvements" / sub).glob("*.png")):
                rel_ref = f"screenshots/ux_improvements/{sub}/{png.name}"
                self.assertIn(rel_ref, ux_doc, f"Unlinked screenshot in UX_STYLE_IMPROVEMENTS.md: {rel_ref}")


class BehavioralAuthTenantAndEdgeProxyTests(unittest.TestCase):
    """Execute `plan-access.js`, `profiles-storage.js`, `auth.js`, and `functions/api/[[path]].js` in runtime."""

    def test_multi_tenant_isolation_privilege_escalation_guards_and_edge_proxy_in_node(self) -> None:
        node_script = r"""
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const appDir = process.env.APP_DIR;

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
    dispatchEvent: () => {},
    addEventListener: () => {}
};
global.CustomEvent = class CustomEvent { constructor(name, opts) { this.name = name; this.detail = opts && opts.detail; } };

const planAccess = require(path.join(appDir, 'plan-access.js'));
assert.strictEqual(planAccess.normalizePlan('free'), 'basic');
assert.strictEqual(planAccess.normalizePlan('trial'), 'basic');
assert.strictEqual(planAccess.normalizePlan('pro'), 'advance');
assert.strictEqual(planAccess.normalizePlan('enterprise'), 'premium');

const Profiles = require(path.join(appDir, 'profiles-storage.js'));
const Auth = require(path.join(appDir, 'auth.js'));

assert.strictEqual(Profiles.isAuthenticated(), false);
store.setItem('bookkeeping_history_v2', JSON.stringify([{ id: 'unauth-leak' }]));
const snap0 = Profiles.getServerStateSnapshot();
assert.strictEqual(Boolean(snap0['profile:unauthenticated::bookkeeping_history_v2']), true);
assert.strictEqual(Boolean(snap0['bookkeeping_history_v2']), false);
assert.strictEqual(backing.has('profile:unauthenticated::bookkeeping_history_v2'), false);
assert.strictEqual(backing.has('bookkeeping_history_v2'), false);

store.setItem('lumen_lang', 'ar');
store.setItem('lumen_sidebar_collapsed', '1');
assert.strictEqual(backing.get('lumen_lang'), 'ar');
assert.strictEqual(backing.get('lumen_sidebar_collapsed'), '1');
assert.strictEqual(Boolean(Profiles.getServerStateSnapshot()['lumen_lang']), false);
assert.strictEqual(Boolean(Profiles.getServerStateSnapshot()['lumen_sidebar_collapsed']), false);

return (async () => {
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

    assert.strictEqual(Profiles.setPlan('premium'), false);
    assert.strictEqual(Profiles.getPlan(), 'basic');
    assert.deepStrictEqual(Profiles.listAllAccounts(), []);
    assert.strictEqual(Profiles.updateAccountAdmin(reg.accountId, { plan: 'premium' }), false);
    assert.strictEqual(Profiles.approvePlanRequest(reg.accountId, 'advance'), false);
    assert.strictEqual(Profiles.impersonateAccount('owner'), false);

    store.setItem('bookkeeping_history_v2', JSON.stringify([{ id: 'tenant-1-inv', type: 'supplier', hasFile: true }]));
    assert.strictEqual(backing.has('bookkeeping_history_v2'), false);
    for (const k of backing.keys()) {
        assert(
            k === 'lumen_lang' || k === 'lumen_sidebar_collapsed' || k.startsWith('lumen_table_page_size:') || k === 'probe',
            'Unexpected non-config key in physical localStorage: ' + k
        );
    }

    const adminVectorHash = await Auth.hashPassword('LumenAdmin2026', '4c756d656e41646d696e53616c743236');
    assert.strictEqual(
        adminVectorHash,
        'pbkdf2_sha256$120000$70663afeba18d22eefd9f653155db1ccbb1a28718290cb662da2a408aceee2b4'
    );
    const rawTenantCreds = await Auth.buildCredentials('tenant1@example.com', 'StrongPassword!123');
    assert(String(rawTenantCreds.passwordHash).startsWith('pbkdf2_sha256$120000$'));
    assert.strictEqual(await Auth.signIn('tenant1@example.com', 'WrongPass'), false);
    assert.strictEqual(await Auth.signIn('  TENANT1@example.com ', 'StrongPassword!123'), true);

    Profiles.requestPlanUpgrade('advance', 'monthly');
    assert.strictEqual(await Auth.signInAdmin('admin@lumenconsultancy.net', 'LumenAdmin2026'), true);
    assert.strictEqual(Profiles.isOwner(), true);
    assert.strictEqual(Profiles.listAllAccounts().length >= 1, true);
    const pwdChangeRes = await Auth.changeAdminPassword('NewAdminPass99', 'NewAdminPass99');
    assert.strictEqual(pwdChangeRes.ok, true);
    assert.strictEqual(backing.has('lumen_admin_credentials'), false);
    await Auth.changeAdminPassword('LumenAdmin2026', 'LumenAdmin2026');
    assert.strictEqual(Profiles.approvePlanRequest(reg.accountId, 'advance'), true);
    assert.strictEqual(Profiles.findAccountByEmail('tenant1@example.com').plan, 'advance');

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
        crypto: global.crypto || (typeof crypto !== 'undefined' ? crypto : undefined),
        TextEncoder,
        fetch: async (url, init) => {
            if (shouldThrowFetch) throw new Error('ECONNREFUSED');
            lastFetched = { url, init };
            return new Response(JSON.stringify({ text: 'ok' }), { status: 200, headers: { 'Content-Type': 'application/json' } });
        }
    };
    vm.runInNewContext(edgeSrc, edgeSandbox);
    const { onRequest } = edgeMod.exports;

    const res405 = await onRequest({ request: new Request('https://lumen-bookkeeping.pages.dev/api/v1/prediction/1', { method: 'DELETE' }), env: { AGY_BACKEND_URL: 'https://backend.example.com' } });
    assert.strictEqual(res405.status, 405);
    const res401Get = await onRequest({ request: new Request('https://lumen-bookkeeping.pages.dev/api/v1/ping', { method: 'GET' }), env: { AGY_BACKEND_URL: 'https://backend.example.com' } });
    assert.strictEqual(res401Get.status, 401);
    const res403 = await onRequest({
        request: new Request('https://lumen-bookkeeping.pages.dev/api/v1/prediction/1', { method: 'POST', headers: { 'X-Lumen-Client': 'lumen-bookkeeping-web', 'Origin': 'https://evil.example.com' }, body: '{}' }),
        env: { AGY_BACKEND_URL: 'https://backend.example.com' }
    });
    assert.strictEqual(res403.status, 403);
    const res503 = await onRequest({
        request: new Request('https://lumen-bookkeeping.pages.dev/api/v1/prediction/1', { method: 'POST', headers: { 'X-Lumen-Client': 'lumen-bookkeeping-web', 'Origin': 'https://lumen-bookkeeping.pages.dev' }, body: '{}' }),
        env: {}
    });
    assert.strictEqual(res503.status, 503);

    shouldThrowFetch = true;
    const res502 = await onRequest({
        request: new Request('https://lumen-bookkeeping.pages.dev/api/v1/prediction/1', { method: 'POST', headers: { 'X-Lumen-Client': 'lumen-bookkeeping-web', 'Origin': 'https://lumen-bookkeeping.pages.dev' }, body: '{}' }),
        env: { AGY_BACKEND_URL: 'https://backend.example.com', AGY_API_SECRET: 'sec-123' }
    });
    assert.strictEqual(res502.status, 502);
    shouldThrowFetch = false;
    const res200 = await onRequest({
        request: new Request('https://lumen-bookkeeping.pages.dev/api/v1/prediction/1', { method: 'POST', headers: { 'X-Lumen-Client': 'lumen-bookkeeping-web', 'Origin': 'https://lumen-bookkeeping.pages.dev' }, body: '{"question":"hi"}' }),
        env: { AGY_BACKEND_URL: 'https://backend.example.com', AGY_API_SECRET: 'sec-123' }
    });
    assert.strictEqual(res200.status, 200);
    assert.strictEqual(lastFetched.init.headers.get('X-Agy-Proxy-Secret'), 'sec-123');

    const d1Tables = { app_state: new Map(), attachments: new Map() }, r2Objects = new Map();
    const fakeD1 = {
        async batch(stmts) {
            const out = [];
            for (const s of stmts) out.push(await s.run());
            return out;
        },
        prepare(sql) {
            return {
                _sql: sql, _args: [],
                bind(...args) { this._args = args; return this; },
                async run() {
                    if (this._sql.includes('INSERT INTO app_state')) d1Tables.app_state.set(String(this._args[0]), String(this._args[1]));
                    else if (this._sql.includes('DELETE FROM app_state WHERE key =')) d1Tables.app_state.delete(String(this._args[0]));
                    else if (this._sql.includes('DELETE FROM app_state')) d1Tables.app_state.clear();
                    else if (this._sql.includes('INSERT INTO attachments')) d1Tables.attachments.set(String(this._args[0]), String(this._args[1]));
                    else if (this._sql.includes('DELETE FROM attachments WHERE key =')) d1Tables.attachments.delete(String(this._args[0]));
                    return { success: true };
                },
                async all() { return { results: Array.from(d1Tables.app_state.entries()).map(([key, value]) => ({ key, value })) }; },
                async first() {
                    const m = this._sql.includes('FROM app_state') ? d1Tables.app_state : d1Tables.attachments;
                    const val = m.get(String(this._args[0]));
                    return val !== undefined ? (this._sql.includes('FROM app_state') ? { value: val } : { data: val }) : null;
                }
            };
        }
    };
    const fakeR2 = {
        async put(k, v) { r2Objects.set(k, String(v)); },
        async get(k) { return r2Objects.has(k) ? { async text() { return r2Objects.get(k); } } : null; },
        async delete(k) { r2Objects.delete(k); }
    };
    const edgeEnvD1 = { LUMEN_DB: fakeD1, LUMEN_ATTACHMENTS: fakeR2, LUMEN_SESSION_SECRET: 'edge-sess-sec' };
    await onRequest({
        request: new Request('https://lumen-bookkeeping.pages.dev/api/v1/state', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-Lumen-Client': 'lumen-bookkeeping-web', 'Origin': 'https://lumen-bookkeeping.pages.dev', 'X-Lumen-Account': 'owner' },
            body: JSON.stringify({ set: {
                lumen_accounts: JSON.stringify({
                    'acc-a': { email: 'a@co.ae', companyName: 'Co A', plan: 'basic', status: 'active', salt: rawTenantCreds.salt, passwordHash: rawTenantCreds.passwordHash },
                    'acc-b': { email: 'b@co.ae', companyName: 'Co B', plan: 'advance', status: 'suspended', salt: 's2', passwordHash: 'h2' }
                }),
                lumen_profiles: JSON.stringify([{ id: 'prof-a', name: 'Co A', accountId: 'acc-a' }, { id: 'prof-b', name: 'Co B', accountId: 'acc-b' }]),
                'profile:prof-a::bookkeeping_history_v2': '[{"id":"inv-a"}]',
                'profile:prof-b::bookkeeping_history_v2': '[{"id":"inv-b"}]',
                lumen_admin_credentials: '{"salt":"adm","passwordHash":"admhash"}'
            } })
        }),
        env: edgeEnvD1
    });

    const resOwnerState = await onRequest({
        request: new Request('https://lumen-bookkeeping.pages.dev/api/v1/state', {
            method: 'GET',
            headers: { 'X-Lumen-Client': 'lumen-bookkeeping-web', 'Origin': 'https://lumen-bookkeeping.pages.dev', 'X-Lumen-Account': 'owner' }
        }),
        env: edgeEnvD1
    });
    assert.strictEqual(Boolean((await resOwnerState.json()).state['lumen_admin_credentials']), false);

    const resUnauthMutate = await onRequest({
        request: new Request('https://lumen-bookkeeping.pages.dev/api/v1/state', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-Lumen-Client': 'lumen-bookkeeping-web', 'Origin': 'https://lumen-bookkeeping.pages.dev' },
            body: JSON.stringify({ set: { 'profile:prof-a::bookkeeping_history_v2': '[]' } })
        }),
        env: edgeEnvD1
    });
    assert.strictEqual((await resUnauthMutate.json()).updated, 0);

    const resEdgeLogin = await onRequest({
        request: new Request('https://lumen-bookkeeping.pages.dev/api/v1/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-Lumen-Client': 'lumen-bookkeeping-web', 'Origin': 'https://lumen-bookkeeping.pages.dev' },
            body: JSON.stringify({ email: 'a@co.ae', password: 'StrongPassword!123' })
        }),
        env: edgeEnvD1
    });
    const edgeLoginData = await resEdgeLogin.json();
    assert.strictEqual(edgeLoginData.ok, true);
    assert.strictEqual(edgeLoginData.accountId, 'acc-a');
    assert(String(edgeLoginData.sessionToken || '').startsWith('sess.acc-a.'));

    const resSuspCfSession = await onRequest({
        request: new Request('https://lumen-bookkeeping.pages.dev/api/v1/auth/session', {
            method: 'GET',
            headers: { 'X-Lumen-Client': 'lumen-bookkeeping-web', 'Origin': 'https://lumen-bookkeeping.pages.dev', 'Cf-Access-Authenticated-User-Email': 'b@co.ae' }
        }),
        env: edgeEnvD1
    });
    assert.strictEqual((await resSuspCfSession.json()).authenticated, false);

    await onRequest({
        request: new Request('https://lumen-bookkeeping.pages.dev/api/v1/attachments', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-Lumen-Client': 'lumen-bookkeeping-web', 'Origin': 'https://lumen-bookkeeping.pages.dev', 'X-Lumen-Account': 'acc-a', 'X-Lumen-Session': edgeLoginData.sessionToken },
            body: JSON.stringify({ key: 'prof-a::att-edge-1', data: 'data:image/png;base64,AAAA' })
        }),
        env: edgeEnvD1
    });
    const resAttGet = await onRequest({
        request: new Request('https://lumen-bookkeeping.pages.dev/api/v1/attachments?key=prof-a%3A%3Aatt-edge-1', {
            method: 'GET',
            headers: { 'X-Lumen-Client': 'lumen-bookkeeping-web', 'Origin': 'https://lumen-bookkeeping.pages.dev', 'X-Lumen-Account': 'acc-a', 'X-Lumen-Session': edgeLoginData.sessionToken }
        }),
        env: edgeEnvD1
    });
    assert.strictEqual((await resAttGet.json()).data, 'data:image/png;base64,AAAA');
    await onRequest({
        request: new Request('https://lumen-bookkeeping.pages.dev/api/v1/attachments', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-Lumen-Client': 'lumen-bookkeeping-web', 'Origin': 'https://lumen-bookkeeping.pages.dev', 'X-Lumen-Account': 'acc-a', 'X-Lumen-Session': edgeLoginData.sessionToken },
            body: JSON.stringify({ remove: ['prof-a::att-edge-1'] })
        }),
        env: edgeEnvD1
    });
    const resAttAfterDel = await onRequest({
        request: new Request('https://lumen-bookkeeping.pages.dev/api/v1/attachments?key=prof-a%3A%3Aatt-edge-1', {
            method: 'GET',
            headers: { 'X-Lumen-Client': 'lumen-bookkeeping-web', 'Origin': 'https://lumen-bookkeeping.pages.dev', 'X-Lumen-Account': 'acc-a', 'X-Lumen-Session': edgeLoginData.sessionToken }
        }),
        env: edgeEnvD1
    });
    assert.strictEqual((await resAttAfterDel.json()).data, null);

    const resTenantA = await onRequest({
        request: new Request('https://lumen-bookkeeping.pages.dev/api/v1/state', {
            method: 'GET',
            headers: { 'X-Lumen-Client': 'lumen-bookkeeping-web', 'Origin': 'https://lumen-bookkeeping.pages.dev', 'X-Lumen-Account': 'acc-a' }
        }),
        env: edgeEnvD1
    });
    const tenantAData = await resTenantA.json();
    assert.strictEqual(Boolean(tenantAData.state['profile:prof-a::bookkeeping_history_v2']), true);
    assert.strictEqual(Boolean(tenantAData.state['profile:prof-b::bookkeeping_history_v2']), false);
    assert.strictEqual(Boolean(tenantAData.state['lumen_admin_credentials']), false);
    const tenantAAccounts = JSON.parse(tenantAData.state.lumen_accounts || '{}');
    assert.strictEqual(Boolean(tenantAAccounts['acc-a']), true);
    assert.strictEqual(Boolean(tenantAAccounts['acc-b']), false);
    assert.strictEqual(Boolean(tenantAAccounts['acc-a'].passwordHash), false);

    await Auth.signInAdmin('admin@lumenconsultancy.net', 'LumenAdmin2026');
    Profiles.updateAccountAdmin(reg.accountId, { plan: 'basic' });
    await Auth.signIn('tenant1@example.com', 'StrongPassword!123');
    assert.strictEqual(Profiles.getPlan(), 'basic');
    const PlanGate = require(path.join(appDir, 'plan-gating.js'));
    assert.strictEqual(PlanGate.canOpen('view-dashboard'), true);
    assert.strictEqual(PlanGate.canOpen('view-audit'), false);
    assert.strictEqual(PlanGate.canOpen('view-equity-statement'), false);
    assert.strictEqual(PlanGate.canOpen('view-tax'), false);

    const Attachments = require(path.join(appDir, 'attachments-store.js'));
    const offloaded = Attachments.offload([{ id: 'inv-att-1', fileBase64: 'data:image/png;base64,BBBB' }]);
    assert.strictEqual(offloaded[0].fileBase64, undefined);
    assert.strictEqual(offloaded[0].hasFile, true);
    assert.strictEqual(await Attachments.load('inv-att-1'), 'data:image/png;base64,BBBB');
    await Attachments.remove('inv-att-1');
    await Attachments.flush();

    const serverStateFromComputerA = Profiles.getServerStateSnapshot();
    Profiles.signOut();
    backing.clear();
    global.window.fetch = async () => ({
        ok: true,
        status: 200,
        json: async () => ({ status: 'ok', state: serverStateFromComputerA })
    });
    await Profiles.syncFromServer();
    assert.strictEqual(await Auth.signInAdmin('admin@lumenconsultancy.net', 'LumenAdmin2026'), true);
    const seenTenant = Profiles.listAllAccounts().find((a) => a.id === reg.accountId);
    assert(seenTenant);
    assert.strictEqual(seenTenant.companyName, 'Tenant One LLC');
    assert.strictEqual(seenTenant.uploadedInvoices, 1);
    Profiles.updateAccountAdmin(reg.accountId, { status: 'suspended', plan: 'basic' });
    assert.strictEqual(Profiles.impersonateAccount(reg.accountId), true);
    assert.strictEqual(Profiles.isImpersonating(), true);
    assert.strictEqual(Profiles.getPlan(), 'premium');
    assert.strictEqual(PlanGate.canOpen('view-audit'), true);
    const ledgerOnCompB = JSON.parse(store.getItem('bookkeeping_history_v2') || '[]');
    assert.strictEqual(ledgerOnCompB.length, 1);
    assert.strictEqual(ledgerOnCompB[0].id, 'tenant-1-inv');

    console.log(JSON.stringify({ status: 'ok' }));
})();
"""
        proc = run_node_script(node_script, APP_DIR)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout.strip().splitlines()[-1])
        self.assertEqual(payload["status"], "ok")

        script_js = "\n".join(
            [(APP_DIR / "script.js").read_text(encoding="utf-8"), *(p.read_text(encoding="utf-8") for p in sorted(APP_DIR.glob("app-*.js")))]
        )
        self.assertIn("targetEl.classList.contains('app-view')", script_js)
        self.assertIn("window.LumenPlanGate.canOpen(targetId)", script_js)

        for doc_rel in ("docs/product/prd-product-requirements.md", "docs/product/user-guide-and-release-notes.md"):
            doc_text = (REPO_ROOT / doc_rel).read_text(encoding="utf-8")
            self.assertIn("Corporate Tax Only (0% VAT)", doc_text)
            self.assertIn("PBKDF2-SHA256 (120,000 iterations)", doc_text)
        for doc_rel in (
            "README.md",
            "docs/product/prd-product-requirements.md",
            "docs/product/user-guide-and-release-notes.md",
            "docs/technical/architecture-and-execution-flow.md",
            "docs/technical/sdd-system-design.md",
            "docs/technical/operational-runbook.md",
        ):
            self.assertNotIn("lumen_attachments_v1", (REPO_ROOT / doc_rel).read_text(encoding="utf-8"))

        style_bundle = "\n".join((APP_DIR / name).read_text(encoding="utf-8") for name in ("style.css", "components.css", "theme-pro.css", "welcome.css", "admin.css"))
        for token in ("--color-surface-canvas", "--color-surface-elevated", "--color-border-focus", "tabular-nums"):
            self.assertIn(token, style_bundle)
        html_bundle = "\n".join([(APP_DIR / "index.html").read_text(encoding="utf-8"), *(p.read_text(encoding="utf-8") for p in sorted(APP_DIR.glob("views-*.js")))])
        for ux_id in ("btnSidebarToggle", "btnQuickJump", "quickJumpModal", "quickJumpInput", "quickJumpList"):
            self.assertIn(ux_id, html_bundle)
        self.assertIn("sidebar-collapsed", script_js)


if __name__ == "__main__":
    unittest.main()
