"""Unit and real-DOM component tests for the React SPA architecture migration.

User stories covered:
1. As a developer maintaining Lumen Books, `index.html` is a clean React SPA shell (`#root`)
   with a minimal entrypoint instead of 50 separate global `<script>` tags.
2. As a frontend engineer, UI components (`<LumenApp />`, `<SidebarNav />`, `<Topbar />`,
   `<DashboardView />`, `<HeroKpiGrid />`, `<CorporateTaxTrackerWidget />`,
   `<UaeComplianceReminderWidget />`, `<NotFoundView />`) render declaratively via React
   (`React.createElement`, `React.html`, hooks, and `ReactDOM.createRoot`).
3. As a multi-tenant user switching profiles or routes, server state is scoped via centralized
   query key factories (`LumenQueryKeys`), mutations support optimistic updates with rollback,
   and URL hash/query state stays in two-way sync with the viewport (`LumenReactStore`).
"""

from __future__ import annotations

import re
import unittest

from tests.dom_harness import APP_DIR, DomComponentHarness


class ReactSpaEntrypointAndBundleTests(unittest.TestCase):
    """Verify `index.html` is a clean React SPA shell without 50 `<script>` tags."""

    def test_index_html_mounts_react_root_with_minimal_script_tags(self) -> None:
        index_html = (APP_DIR / "index.html").read_text(encoding="utf-8")
        script_tags = re.findall(r"<script\b[^>]*>", index_html, flags=re.IGNORECASE)
        self.assertIn('<div id="root"></div>', index_html)
        self.assertLessEqual(len(script_tags), 6, f"Expected <= 6 script tags, found {len(script_tags)}")
        for required_script in ("react-runtime.js", "react-store.js", "views-dashboard.js", "react-app.js"):
            self.assertIn(required_script, index_html)
            self.assertTrue((APP_DIR / required_script).is_file(), f"Missing {required_script}")

    def test_react_app_manifest_preserves_deterministic_module_load_order(self) -> None:
        react_app_src = (APP_DIR / "react-app.js").read_text(encoding="utf-8")
        self.assertIn("LUMEN_MODULE_MANIFEST", react_app_src)
        ordered = (
            "profiles-storage.js", "auth.js", "ui-feedback.js", "views-transactions.js", "views-modals.js",
            "profiles-ui.js", "plan-gating.js", "vat201.js", "corp-tax-tracker.js", "compliance-reminders.js",
            "whatsapp-workflows.js", "wps-gratuity.js", "credit-notes.js", "app-core-and-router.js", "script.js",
            "faf-export.js", "fx-correction.js", "i18n.js", "ui-forms.js", "ui-tables.js", "ui-layout.js",
        )
        positions = [react_app_src.index(name) for name in ordered]
        self.assertEqual(positions, sorted(positions), "Module manifest order violated")

    def test_welcome_and_admin_entrypoints_mount_react_roots_for_devtools(self) -> None:
        welcome_html = (APP_DIR / "welcome.html").read_text(encoding="utf-8")
        admin_html = (APP_DIR / "admin.html").read_text(encoding="utf-8")
        self.assertIn("react-runtime.js", welcome_html)
        self.assertIn('id="welcomeRoot"', welcome_html)
        self.assertIn("mountDeclarativeRoot", welcome_html)
        self.assertIn("react-runtime.js", admin_html)
        self.assertIn('id="adminRoot"', admin_html)
        self.assertIn("mountDeclarativeRoot", admin_html)


class ReactRuntimeHooksAndReconcilerTests(unittest.TestCase):
    """Verify `react-runtime.js` hooks, context, memoization, and DOM reconciliation in Chromium."""

    def setUp(self) -> None:
        self.dom = DomComponentHarness()
        self.dom.mount('<div id="testRoot"></div>', modules=("react-runtime.js",))

    def test_use_state_use_effect_use_memo_use_context_and_event_handling(self) -> None:
        result = self.dom.run("""
            const {
                createElement: h, html, createContext, useState, useReducer,
                useEffect, useMemo, useCallback, useRef, useContext, memo
            } = window.React;
            const { createRoot, flushSync } = window.ReactDOM;

            const ThemeCtx = createContext('navy');
            const effectLog = [];
            let childRenders = 0;

            const MemoBadge = memo(function Badge({ label }) {
                childRenders += 1;
                const theme = useContext(ThemeCtx);
                return html`<span id="memoBadge" data-theme=${theme}>${label}</span>`;
            });

            function CounterApp() {
                const [count, setCount] = useState(2);
                const [step, dispatchStep] = useReducer((s, a) => a === 'inc' ? s + 1 : s, 1);
                const doubled = useMemo(() => count * 2, [count]);
                const btnRef = useRef(null);
                const handleAdd = useCallback(() => setCount((c) => c + step), [step]);

                useEffect(() => {
                    effectLog.push('mount:' + count);
                    return () => effectLog.push('cleanup:' + count);
                }, [count]);

                return html`
                    <${ThemeCtx.Provider} value="enterprise-navy">
                        <div className="counter-card">
                            <p id="countVal" data-doubled=${String(doubled)}>${String(count)}</p>
                            <button id="incBtn" ref=${btnRef} type="button" onClick=${handleAdd}>Add</button>
                            <button id="stepBtn" type="button" onClick=${() => dispatchStep('inc')}>Step</button>
                            <${MemoBadge} label="Stable" />
                        </div>
                    <//>
                `;
            }

            const container = document.getElementById('testRoot');
            const root = createRoot(container);
            flushSync(() => root.render(h(CounterApp)));

            const initialText = document.getElementById('countVal').textContent;
            const initialTheme = document.getElementById('memoBadge').dataset.theme;
            const rendersAfterMount = childRenders;

            document.getElementById('incBtn').click();
            await tick(20);
            const afterFirstClick = document.getElementById('countVal').textContent;
            const doubledAttr = document.getElementById('countVal').dataset.doubled;
            const rendersAfterSameLabel = childRenders;

            document.getElementById('stepBtn').click();
            await tick(20);
            document.getElementById('incBtn').click();
            await tick(20);
            const afterStepClick = document.getElementById('countVal').textContent;

            root.unmount();
            done({
                version: window.React.version, initialText, initialTheme, afterFirstClick, doubledAttr,
                afterStepClick, rendersAfterMount, rendersAfterSameLabel, effectLog, unmountedEmpty: container.innerHTML === '',
            });
        """)
        self.assertTrue(result["version"].startswith("18.") and result["unmountedEmpty"])
        self.assertEqual((result["initialText"], result["initialTheme"], result["afterFirstClick"], result["doubledAttr"], result["afterStepClick"]), ("2", "enterprise-navy", "3", "6", "5"))
        self.assertEqual((result["rendersAfterMount"], result["rendersAfterSameLabel"]), (1, 1))
        for expected_evt in ("mount:2", "cleanup:2", "mount:3"):
            self.assertIn(expected_evt, result["effectLog"])

    def test_react_devtools_global_hook_injection_and_fiber_tree_commit(self) -> None:
        result = self.dom.run("""
            const injectedRenderers = [];
            const committedRoots = [];
            const fakeHook = {
                supportsFiber: true,
                isDisabled: false,
                renderers: new Map(),
                fiberRoots: {},
                inject(internals) {
                    const id = injectedRenderers.length + 1;
                    injectedRenderers.push(internals);
                    this.renderers.set(id, internals);
                    this.fiberRoots[id] = new Set();
                    return id;
                },
                getFiberRoots(id) {
                    if (!this.fiberRoots[id]) this.fiberRoots[id] = new Set();
                    return this.fiberRoots[id];
                },
                onCommitFiberRoot(rendererID, root, priorityLevel, didError) {
                    committedRoots.push({ rendererID, root, didError });
                },
                onCommitFiberUnmount() {},
            };
            window.__REACT_DEVTOOLS_GLOBAL_HOOK__ = fakeHook;
            if (typeof window.ReactDOM.__connectDevToolsHook === 'function') {
                window.ReactDOM.__connectDevToolsHook(fakeHook);
            }

            const { createElement: h, html } = window.React;
            const { createRoot, flushSync, mountDeclarativeRoot } = window.ReactDOM;

            function WelcomeBanner() {
                return html`
                    <section id="devtoolsBanner">
                        <h1>Lumen React DevTools</h1>
                        <a id="unsafeJsLink" href="javascript:void(0)">Blocked</a>
                        <a id="unsafeDataLink" href="data:text/html,<script>1</script>">BlockedData</a>
                        <a id="safeHttpsLink" href="https://lumenconsultancy.net">Safe</a>
                    </section>
                `;
            }

            const container = document.getElementById('testRoot');
            const root = createRoot(container);
            flushSync(() => root.render(h(WelcomeBanner)));

            const bannerEl = document.getElementById('devtoolsBanner');
            const containerKeys = Object.keys(container);
            const bannerKeys = bannerEl ? Object.keys(bannerEl) : [];
            const fiberKey = bannerKeys.find((k) => k.startsWith('__reactFiber$'));
            const containerKey = containerKeys.find((k) => k.startsWith('__reactContainer$'));
            const lastCommit = committedRoots[committedRoots.length - 1];
            const hostRoot = lastCommit ? lastCommit.root.current : null;

            // Also verify mountDeclarativeRoot on a static container (as used on /welcome and /admin)
            let hookRunCount = 0;
            window.__lumenPageMountHooks = Object.assign(window.__lumenPageMountHooks || {}, {
                WelcomeApp: () => { hookRunCount += 1; },
            });
            const staticBox = document.createElement('div');
            staticBox.id = 'welcomeRoot';
            staticBox.innerHTML = '<header class="topbar"><a href="/welcome" id="brandLink">Lumen Books</a></header>';
            document.body.appendChild(staticBox);
            if (typeof mountDeclarativeRoot === 'function') {
                mountDeclarativeRoot(staticBox, 'WelcomeApp');
                mountDeclarativeRoot(staticBox, 'WelcomeApp');
            }

            done({
                injectedCount: injectedRenderers.length,
                rendererPkg: injectedRenderers[0] ? injectedRenderers[0].rendererPackageName : null,
                committedCount: committedRoots.length,
                hasReactRootContainer: !!container._reactRootContainer,
                hasContainerKey: !!containerKey,
                hasFiberKey: !!fiberKey,
                hostRootTag: hostRoot ? hostRoot.tag : null,
                hasMountedElementState: !!(hostRoot && hostRoot.memoizedState && hostRoot.memoizedState.element),
                childComponentTag: hostRoot && hostRoot.child ? hostRoot.child.tag : null,
                childComponentName: hostRoot && hostRoot.child && hostRoot.child.type ? hostRoot.child.type.name : null,
                welcomeMountedRoot: !!staticBox._reactRootContainer,
                welcomeHookRunCount: hookRunCount,
                welcomeBrandHref: document.getElementById('brandLink') ? document.getElementById('brandLink').getAttribute('href') : null,
                unsafeJsHref: document.getElementById('unsafeJsLink') ? document.getElementById('unsafeJsLink').getAttribute('href') : null,
                unsafeDataHref: document.getElementById('unsafeDataLink') ? document.getElementById('unsafeDataLink').getAttribute('href') : null,
                safeHttpsHref: document.getElementById('safeHttpsLink') ? document.getElementById('safeHttpsLink').getAttribute('href') : null,
            });
        """)
        self.assertGreaterEqual(result["injectedCount"], 1)
        self.assertEqual(result["rendererPkg"], "react-dom")
        self.assertGreaterEqual(result["committedCount"], 2)
        self.assertTrue(result["hasReactRootContainer"])
        self.assertTrue(result["hasContainerKey"])
        self.assertTrue(result["hasFiberKey"])
        self.assertEqual(result["hostRootTag"], 3)
        self.assertTrue(result["hasMountedElementState"])
        self.assertEqual(result["childComponentTag"], 0)
        self.assertEqual(result["childComponentName"], "WelcomeBanner")
        self.assertTrue(result["welcomeMountedRoot"])
        self.assertEqual(result["welcomeHookRunCount"], 1)
        self.assertEqual(result["welcomeBrandHref"], "/welcome")
        self.assertIsNone(result["unsafeJsHref"])
        self.assertIsNone(result["unsafeDataHref"])
        self.assertEqual(result["safeHttpsHref"], "https://lumenconsultancy.net")


class ReactStoreQueryKeysAndRouterTests(unittest.TestCase):
    """Verify `react-store.js` query key scoping, optimistic mutations, retry bounds, and URL sync."""

    def setUp(self) -> None:
        self.dom = DomComponentHarness()
        self.dom.mount(
            '<div id="root"></div>',
            modules=("react-runtime.js", "react-store.js"),
        )

    def test_query_key_factory_tenant_isolation_optimistic_rollback_and_retry_policy(self) -> None:
        result = self.dom.run("""
            const { LumenQueryKeys, LumenQueryCache } = window;
            const ctxA = { accountId: 'acc_tenant_a', profileId: 'prof_1' };
            const ctxB = { accountId: 'acc_tenant_b', profileId: 'prof_1' };

            // Verify resolveContext() without explicit arguments reads active account/profile from LumenProfiles
            window.LumenProfiles = {
                currentAccount: () => ({ id: 'acc_live_tenant' }),
                active: () => ({ id: 'prof_live_co' }),
            };
            const resolvedFromProfiles = LumenQueryKeys.resolveContext();
            delete window.LumenProfiles;

            const keyA = LumenQueryKeys.ledger(ctxA, { status: 'posted' });
            const keyB = LumenQueryKeys.ledger(ctxB, { status: 'posted' });

            LumenQueryCache.setQueryData(keyA, [{ id: 'INV-1', total: 100 }], ctxA);
            const validForA = LumenQueryCache.getQueryData(keyA, ctxA);
            const leakedToB = LumenQueryCache.getQueryData(keyA, ctxB);

            // Optimistic update that succeeds
            await LumenQueryCache.mutateOptimistic({
                queryKey: keyA,
                context: ctxA,
                optimisticUpdater: (prev) => [...(prev || []), { id: 'INV-2', total: 250 }],
                mutationFn: async () => [{ id: 'INV-1', total: 100 }, { id: 'INV-2', total: 250 }],
            });
            const afterSuccess = LumenQueryCache.getQueryData(keyA, ctxA);

            // Optimistic update that fails -> must roll back to snapshot
            let sawOptimistic = null;
            let caughtError = false;
            try {
                await LumenQueryCache.mutateOptimistic({
                    queryKey: keyA,
                    context: ctxA,
                    optimisticUpdater: (prev) => [...prev, { id: 'INV-BAD', total: 999 }],
                    mutationFn: async () => {
                        sawOptimistic = LumenQueryCache.getQueryData(keyA, ctxA).length;
                        throw new Error('Server 500 write failure');
                    },
                });
            } catch (e) {
                caughtError = true;
            }
            const afterRollback = LumenQueryCache.getQueryData(keyA, ctxA);

            done({
                 resolvedFromProfiles, keyA, keyB, validLen: validForA ? validForA.length : 0, leakedToB,
                afterSuccessLen: afterSuccess.length, sawOptimistic, caughtError, afterRollbackLen: afterRollback.length,
                retry400: LumenQueryCache.shouldRetry(400, 0), retry401: LumenQueryCache.shouldRetry(401, 0),
                retry403: LumenQueryCache.shouldRetry(403, 0), retry404: LumenQueryCache.shouldRetry(404, 0),
                retry503First: LumenQueryCache.shouldRetry(503, 1), retry503Exceeded: LumenQueryCache.shouldRetry(503, 4),
            });
        """)
        self.assertEqual(result["resolvedFromProfiles"], {"accountId": "acc_live_tenant", "profileId": "prof_live_co"})
        self.assertNotEqual(result["keyA"], result["keyB"])
        self.assertEqual((result["validLen"], result["leakedToB"], result["afterSuccessLen"], result["sawOptimistic"], result["afterRollbackLen"]), (1, None, 2, 3, 2))
        self.assertTrue(result["caughtError"] and result["retry503First"])
        self.assertFalse(any((result["retry400"], result["retry401"], result["retry403"], result["retry404"], result["retry503Exceeded"])))


class ReactAppShellAndDashboardMountTests(unittest.TestCase):
    """Verify `<LumenApp />` mounts the shell, dashboard KPIs, and contextual NotFound view."""

    def setUp(self) -> None:
        self.dom = DomComponentHarness()
        self.dom.mount(
            '<div id="root"></div>',
            modules=("react-runtime.js", "react-store.js", "views-dashboard.js"),
        )

    def test_lumen_app_renders_shell_dashboard_and_bidirectional_route_states(self) -> None:
        result = self.dom.run("""
            const { createElement: h } = window.React;
            const { createRoot, flushSync } = window.ReactDOM;
            const { LumenApp } = window.LumenReactViews;
            const store = window.LumenReactStore;

            const root = createRoot(document.getElementById('root'));
            flushSync(() => root.render(h(LumenApp)));
            store.bindRuntimeBridge();

            const initialTitle = document.getElementById('pageTitle').textContent;
            const hasCorpTaxCard = !!document.getElementById('corpTaxTrackerCard');
            const hasComplianceCard = !!document.getElementById('uaeComplianceReminderCard');
            const navCount = document.querySelectorAll('.sidebar-nav .nav-item[data-target]').length;

            // Outbound dashboard period query synchronization + invalid period canonicalization
            const periodResult = store.setDashboardPeriod('2026', '2');
            const periodSearch = periodResult.query;
            store.setDashboardPeriod('invalid-year', '99');
            const canonicalPeriod = {
                year: store.getState().dashboardYear,
                month: store.getState().dashboardMonth,
                search: store.getState().dashboardQuery,
            };

            // Navigate to a valid view
            store.navigateToView('view-customer', 'Sales Invoices');
            await tick(20);
            const salesHash = window.location.hash;
            const salesTitle = document.getElementById('pageTitle').textContent;

            // Navigate to an unknown view via real browser location.hash -> contextual NotFound fallback
            window.location.hash = '#view-missing-xyz';
            await tick(40);
            const notFoundEl = document.getElementById('reactNotFoundView');
            const notFoundVisible = !!notFoundEl && !notFoundEl.hidden;
            const dashDisplayOnUnknown = document.getElementById('view-dashboard').style.display;

            // Recover back to dashboard via NotFound button
            document.getElementById('btnReturnDashboard').click();
            await tick(20);
            const recoveredView = store.getState().activeView;
            const dashDisplayAfterRecover = document.getElementById('view-dashboard').style.display;

            done({
                initialTitle, hasCorpTaxCard, hasComplianceCard, navCount, periodSearch, canonicalPeriod,
                salesHash, salesTitle, notFoundVisible, dashDisplayOnUnknown, recoveredView, dashDisplayAfterRecover,
            });
        """)
        self.assertEqual((result["initialTitle"], result["salesHash"], result["salesTitle"], result["recoveredView"]), ("Dashboard", "#view-customer", "Sales Invoices", "view-dashboard"))
        self.assertTrue(result["hasCorpTaxCard"] and result["hasComplianceCard"] and result["notFoundVisible"] and result["navCount"] >= 25)
        self.assertIn("year=2026", result["periodSearch"])
        self.assertIn("month=2", result["periodSearch"])
        self.assertEqual(result["canonicalPeriod"], {"year": "all", "month": "all", "search": ""})
        self.assertEqual((result["dashDisplayOnUnknown"], result["dashDisplayAfterRecover"]), ("none", "block"))

    def test_sidebar_collapsed_mode_renders_svg_icons_for_all_menu_items(self) -> None:
        result = self.dom.run("""
            const { createElement: h } = window.React;
            const { createRoot, flushSync } = window.ReactDOM;
            const { LumenApp } = window.LumenReactViews;

            const root = createRoot(document.getElementById('root'));
            flushSync(() => root.render(h(LumenApp)));

            const navItems = Array.from(document.querySelectorAll('.sidebar-nav .nav-item[data-target]'));
            const missingSvgTargets = navItems
                .filter((item) => !item.querySelector('svg'))
                .map((item) => item.getAttribute('data-target'));

            document.body.classList.add('sidebar-collapsed');
            await tick(20);

            const bankItem = document.querySelector('.sidebar-nav .nav-item[data-target="view-bank"]');
            const bankSvg = bankItem ? bankItem.querySelector('svg') : null;
            const bankSvgRect = bankSvg ? bankSvg.getBoundingClientRect() : { width: 0, height: 0 };
            const bankBeforeContent = bankItem ? getComputedStyle(bankItem, '::before').content : '';
            const pdcCardPresent = !!document.getElementById('pdcReminderCard');

            done({
                totalNavItems: navItems.length,
                missingSvgTargets,
                bankSvgWidth: Math.round(bankSvgRect.width),
                bankSvgHeight: Math.round(bankSvgRect.height),
                bankBeforeContent,
                pdcCardPresent,
            });
        """)
        self.assertGreaterEqual(result["totalNavItems"], 31)
        self.assertEqual(
            result["missingSvgTargets"],
            [],
            f"All sidebar menu items must have an SVG icon; missing on: {result['missingSvgTargets']}",
        )
        self.assertGreaterEqual(result["bankSvgWidth"], 16)
        self.assertGreaterEqual(result["bankSvgHeight"], 16)
        self.assertIn(result["bankBeforeContent"], ("none", "normal", '""'))
        self.assertTrue(result["pdcCardPresent"])

    def test_three_phase_typescript_and_official_react_18_migration(self) -> None:
        import json
        from tests.js_runner import run_node_script
        tsconfig = json.loads((APP_DIR / "tsconfig.json").read_text(encoding="utf-8"))
        self.assertTrue(tsconfig["compilerOptions"]["allowJs"] and tsconfig["compilerOptions"]["strict"])
        self.assertIn("functions/**/*.ts", tsconfig["include"])
        self.assertTrue((APP_DIR / "vite.config.ts").is_file())
        accounting_types = (APP_DIR / "types" / "accounting.ts").read_text(encoding="utf-8")
        for iface in ("ChartOfAccountEntry", "LedgerEntry", "InvoiceDocument", "EmployeeProfile", "Vat201Report"):
            self.assertIn(f"interface {iface}", accounting_types)
        forbidden_type_re = re.compile(
            r":\s*any\b|\bas\s+any\b|<any>|ReturnType\s*<\s*typeof\s+JSON\.parse\s*>|\bLumenValue\b|\bLumenRecord\b|@ts-ignore|@ts-expect-error"
        )
        for ts_mod in (
            "src/react-runtime.ts", "vat201.ts", "wps-gratuity.ts", "corp-tax-tracker.ts", "faf-export.ts", "fx-correction.ts", "react-store.ts",
            "welcome-plans.ts", "plan-access.ts", "auth.ts", "profiles-storage.ts", "attachments-store.ts",
            "ar-posting-fix.ts", "einvoice-ae.ts", "i18n.ts", "functions/api/[[path]].ts",
        ):
            src_txt = (APP_DIR / ts_mod).read_text(encoding="utf-8")
            self.assertNotIn("inner" + "HTML", src_txt, f"Unexpected raw HTML sink in {ts_mod}")
            self.assertNotIn("new " + "Function", src_txt, f"Unexpected dynamic code sink in {ts_mod}")
            self.assertIsNone(forbidden_type_re.search(src_txt), f"Unexpected forbidden type/evasion in {ts_mod}")
        for tsx_mod in (
            "react-app.tsx", "views-dashboard.tsx", "views-transactions.tsx", "views-workforce-and-quotes.tsx",
            "views-operations.tsx", "views-accounting-and-tax.tsx", "views-sales-and-banking.tsx",
            "views-reports-and-settings.tsx", "views-modals.tsx", "app-core-and-router.tsx",
            "app-ledger-and-soa.tsx", "app-ledger-actions.tsx", "app-journals-and-coa.tsx",
            "app-supplier-bills.tsx", "app-customer-invoices.tsx", "app-quotes-pos-recurring.tsx",
            "app-contacts-and-inventory.tsx", "app-payroll-and-wps.tsx", "app-assets-and-accruals.tsx",
            "app-banking-and-trial.tsx", "app-bank-statements.tsx", "app-reports-and-fpa.tsx", "app-settings-and-kpis.tsx",
            "admin.tsx", "welcome.tsx", "ui-feedback.tsx", "ui-forms.tsx", "ui-tables.tsx", "ui-layout.tsx",
            "profiles-ui.tsx", "plan-gating.tsx", "compliance-reminders.tsx", "whatsapp-workflows.tsx",
            "credit-notes.tsx", "expenses.tsx", "quote-preview.tsx", "po-preview.tsx", "po-receiving.tsx", "script.tsx",
        ):
            src_txt = (APP_DIR / tsx_mod).read_text(encoding="utf-8")
            self.assertNotIn("inner" + "HTML", src_txt, f"Unexpected raw HTML sink in {tsx_mod}")
            self.assertNotIn("() => true", src_txt, f"Unexpected frozen memo comparator in {tsx_mod}")
            self.assertIsNone(forbidden_type_re.search(src_txt), f"Unexpected forbidden type/evasion in {tsx_mod}")
        for page_js, init_call in (("admin.js", "initAdminConsole()"), ("welcome.js", "initWelcomePortal()")):
            js_src = (APP_DIR / page_js).read_text(encoding="utf-8")
            self.assertLess(js_src.index("window.LumenReactViews = Object.assign"), js_src.rindex(init_call), f"LumenReactViews must register before {init_call} in {page_js}")
        # Execute Phase 2 TypeScript domain unit tests (tests/domain-accounting.test.ts) via js_runner
        ts_run = run_node_script("const path = require('path'); require(path.join(process.env.APP_DIR, 'tests/domain-accounting.test.ts'));", APP_DIR)
        self.assertEqual(ts_run.returncode, 0, f"TypeScript domain tests failed: {ts_run.stderr}")
        self.assertIn("VITEST_PASSED:9", ts_run.stdout)
        dom = DomComponentHarness()
        dom.mount('<div id="root"></div>', modules=("react-runtime.js", "react-store.js", "views-dashboard.js", "views-transactions.js", "views-workforce-and-quotes.js", "views-operations.js"))
        res = dom.run(r"""
            const { createElement: h, htmlToVNode } = window.React;
            const { createRoot, flushSync, renderHtml } = window.ReactDOM;
            const { LumenApp } = window.LumenReactViews;
            const store = window.LumenReactStore;
            flushSync(() => createRoot(document.getElementById('root')).render(h(LumenApp)));
            const vnodeFromOneArg = renderHtml('<span id="oneArgNode">VNode</span>');
            const nullFromTwoArg = renderHtml(null, '<span>NullTarget</span>');
            const scratchBox = document.createElement('div');
            const mountedBox = renderHtml(scratchBox, '<script>window.__xss=1</script><iframe src="javascript:alert(1)"></iframe><a id="jsLink" href="javascript:alert(1)">Bad</a><button id="badClick" onclick="window.__xss=1">Bad</button><button id="goodClick" onclick="editEntry(\'42\')">Good</button>');
            store.setDashboardKpis({ runway: '18.5 Months', revenue: 'AED 125,000.00', netProfit: 'AED 45,000.00', netProfitColor: '#10b981' });
            store.setCorpTaxWidget({ fyRangeText: 'FY 2026', totalBadgeText: 'AED 900.00 CT', taxableIncomeText: 'AED 385,000.00', zeroBandSubText: 'AED 375k Used', nineBandText: 'AED 900.00', nineBandSubText: 'AED 10k @ 9%', fillPercent: 100 });
            store.setComplianceWidget({ badgeText: '1 Action Needed', badgeBg: '#fef3c7', badgeColor: '#92400e', rowsHtml: '<div id="crRow1">VAT Q1 Due</div>' });
            store.setDatalists({ customers: '<option value="Acme LLC"></option>' });
            store.renderSlot('historyBody', '<tr id="declRow"><td><img id="xssProbe" src="x" onerror="window.__xss=1"><button id="safeBtn" onclick="editEntry(\'7\')">Ok</button></td></tr>');
            let editedId = null;
            window.editEntry = (id) => { editedId = id; };
            document.getElementById('safeBtn').click();
            const declRow = document.getElementById('declRow');
            const xssProbe = document.getElementById('xssProbe');
            const hasFiber = declRow ? Object.keys(declRow).some((k) => k.startsWith('__reactFiber$')) : false;
            done({
                vnodeValid: !!(vnodeFromOneArg && vnodeFromOneArg.props), nullReturn: nullFromTwoArg === null, mountedReturn: mountedBox === scratchBox,
                blockedTagsRemoved: !scratchBox.querySelector('script') && !scratchBox.querySelector('iframe'),
                badAttrsRemoved: !scratchBox.querySelector('#jsLink').getAttribute('href') && !scratchBox.querySelector('#badClick').onclick,
                editedId, reactVersion: window.React.version, hasHtmlToVNode: typeof htmlToVNode === 'function',
                hasLedger: !!document.getElementById('view-ledger'), hasCustomer: !!document.getElementById('view-customer'),
                hasTimesheet: !!document.getElementById('view-timesheet'),
                runwayText: document.getElementById('kpiRunway').textContent,
                revenueText: document.getElementById('kpiRevenue').textContent,
                ctTotalText: document.getElementById('ctTotalBadge').textContent,
                crRowPresent: !!document.getElementById('crRow1'),
                datalistHasAcme: document.getElementById('customerList').innerHTML.includes('Acme LLC'),
                slotState: store.getState().slots.historyBody, hasFiber,
                xssNeutralized: !window.__xss && (!xssProbe || !xssProbe.getAttribute('onerror')),
                controllerCount: Object.keys(window.LumenReactControllers || {}).length,
            });
        """)
        self.assertTrue(res["vnodeValid"] and res["nullReturn"] and res["mountedReturn"] and res["blockedTagsRemoved"] and res["badAttrsRemoved"])
        self.assertEqual(res["editedId"], "7")
        self.assertTrue(str(res["reactVersion"]).startswith("18.") and res["hasHtmlToVNode"] and res["xssNeutralized"])
        self.assertTrue(res["hasLedger"] and res["hasCustomer"] and res["hasTimesheet"] and res["hasFiber"])
        self.assertEqual((res["runwayText"], res["revenueText"], res["ctTotalText"]), ("18.5 Months", "AED 125,000.00", "AED 900.00 CT"))
        self.assertTrue(res["crRowPresent"] and res["datalistHasAcme"] and "declRow" in res["slotState"])


if __name__ == "__main__":
    unittest.main()
