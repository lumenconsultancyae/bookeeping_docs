"""Portable JavaScript behavioral test runner using Node.js when available or Headless Chromium V8 fallback."""

from __future__ import annotations

import atexit
import os
from pathlib import Path
import shutil
import subprocess

_PLAYWRIGHT = None
_BROWSER = None
_PAGE = None
_SELENIUM_DRIVER = None
_TS_CACHE: dict[tuple[str, int], str] = {}


def _transpile_ts_file(ts_file: Path, app_dir: Path) -> str:
    key = (str(ts_file), ts_file.stat().st_mtime_ns)
    if key in _TS_CACHE:
        return _TS_CACHE[key]
    src = ts_file.read_text(encoding="utf-8")
    esbuild_bin = app_dir / "node_modules" / "@esbuild" / "linux-arm64" / "bin" / "esbuild"
    if esbuild_bin.exists():
        loader = "tsx" if ts_file.suffix == ".tsx" else "ts"
        res = subprocess.run(
            [str(esbuild_bin), f"--loader={loader}", "--format=cjs", "--jsx=transform", "--jsx-factory=React.createElement", "--jsx-fragment=React.Fragment", "--target=es2020"],
            input=src,
            capture_output=True,
            text=True,
            check=True,
        )
        _TS_CACHE[key] = res.stdout
        return res.stdout
    return src


def _shutdown_playwright() -> None:
    global _PAGE, _BROWSER, _PLAYWRIGHT, _SELENIUM_DRIVER
    for resource, method in (
        (_PAGE, "close"),
        (_BROWSER, "close"),
        (_PLAYWRIGHT, "stop"),
        (_SELENIUM_DRIVER, "quit"),
    ):
        if resource is not None:
            try:
                getattr(resource, method)()
            except Exception:
                pass
    _PAGE = None
    _BROWSER = None
    _PLAYWRIGHT = None
    _SELENIUM_DRIVER = None


def _get_selenium_driver():
    global _SELENIUM_DRIVER
    if _SELENIUM_DRIVER is not None:
        return _SELENIUM_DRIVER
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service

    opts = Options()
    opts.set_capability("goog:loggingPrefs", {"browser": "ALL"})
    for arg in ("--headless=new", "--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"):
        opts.add_argument(arg)
    if Path("/usr/bin/chromium").exists():
        opts.binary_location = "/usr/bin/chromium"
    service = Service("/usr/bin/chromedriver") if Path("/usr/bin/chromedriver").exists() else Service()
    _SELENIUM_DRIVER = webdriver.Chrome(service=service, options=opts)
    _SELENIUM_DRIVER.set_script_timeout(30)
    atexit.register(_shutdown_playwright)
    return _SELENIUM_DRIVER


class _SeleniumLocatorAdapter:
    _RESOLVE_JS = """
    const resolveChain = (chain) => {
        let nodes = [document];
        for (const [sel, hasText] of chain) {
            const next = [];
            for (const root of nodes) {
                for (const el of root.querySelectorAll(sel)) {
                    if (!hasText || String(el.innerText ?? el.textContent ?? '').includes(hasText)) {
                        next.push(el);
                    }
                }
            }
            nodes = next;
        }
        return nodes;
    };
    """

    def __init__(self, page: _SeleniumPageAdapter, selector: str | list[tuple[str, str | None]], *, has_text: str | None = None) -> None:
        self._page = page
        if isinstance(selector, list):
            self._chain = selector
            self._selector = selector[-1][0] if selector else ""
        else:
            self._chain = [(selector, has_text)]
            self._selector = selector

    @property
    def first(self) -> _SeleniumLocatorAdapter:
        return self

    def locator(self, selector: str, *, has_text: str | None = None) -> _SeleniumLocatorAdapter:
        return _SeleniumLocatorAdapter(self._page, [*self._chain, (selector, has_text)])

    def count(self) -> int:
        return int(self._page.evaluate(f"(chain) => {{ {self._RESOLVE_JS} return resolveChain(chain).length; }}", self._chain) or 0)

    def is_visible(self) -> bool:
        return bool(
            self._page.evaluate(
                f"(chain) => {{ {self._RESOLVE_JS} const el = resolveChain(chain)[0]; if (!el) return false; const s = getComputedStyle(el); return s.display !== 'none' && s.visibility !== 'hidden' && (el.offsetWidth > 0 || el.offsetHeight > 0 || el.getClientRects().length > 0); }}",
                self._chain,
            )
        )

    def click(self) -> None:
        self._page.evaluate(
            f"(chain) => {{ {self._RESOLVE_JS} const el = resolveChain(chain)[0]; if (!el) throw new Error('Element not found: ' + JSON.stringify(chain)); el.scrollIntoView({{ block: 'center', inline: 'nearest' }}); el.click(); }}",
            self._chain,
        )

    def inner_text(self) -> str:
        return str(self._page.evaluate(f"(chain) => {{ {self._RESOLVE_JS} const el = resolveChain(chain)[0]; return el ? (el.innerText ?? el.textContent ?? '') : ''; }}", self._chain) or "")

    def inner_html(self) -> str:
        return str(self._page.evaluate(f"(chain) => {{ {self._RESOLVE_JS} const el = resolveChain(chain)[0]; return el ? (el.innerHTML ?? '') : ''; }}", self._chain) or "")

    def input_value(self) -> str:
        return str(self._page.evaluate(f"(chain) => {{ {self._RESOLVE_JS} const el = resolveChain(chain)[0]; return el ? String(el.value ?? '') : ''; }}", self._chain) or "")

    def is_checked(self) -> bool:
        return bool(self._page.evaluate(f"(chain) => {{ {self._RESOLVE_JS} const el = resolveChain(chain)[0]; return Boolean(el && el.checked); }}", self._chain))

    def get_attribute(self, name: str) -> str | None:
        val = self._page.evaluate(f"([chain, attr]) => {{ {self._RESOLVE_JS} const el = resolveChain(chain)[0]; return el ? el.getAttribute(attr) : null; }}", [self._chain, name])
        return str(val) if val is not None else None

    def evaluate(self, expression: str, arg: object = None) -> object:
        return self._page.evaluate(
            f"([chain, arg]) => {{ {self._RESOLVE_JS} const el = resolveChain(chain)[0]; if (!el) throw new Error('Element not found: ' + JSON.stringify(chain)); const fn = {expression}; return fn(el, arg); }}",
            [self._chain, arg],
        )

    def set_input_files(self, file_path: str) -> None:
        from selenium.webdriver.common.by import By

        self._page._driver.find_element(By.CSS_SELECTOR, self._selector).send_keys(str(file_path))


class _SeleniumPageAdapter:
    def __init__(self, driver) -> None:
        self._driver = driver
        self._severe_logs: list[dict[str, str]] = []

    @property
    def url(self) -> str:
        return str(self._driver.current_url or "")

    def is_closed(self) -> bool:
        return False

    def close(self) -> None:
        pass

    def locator(self, selector: str, *, has_text: str | None = None) -> _SeleniumLocatorAdapter:
        return _SeleniumLocatorAdapter(self, selector, has_text=has_text)

    def screenshot(self, *, path: str, timeout: int = 10000) -> None:
        self._driver.save_screenshot(str(path))

    def emulate_media(self, *, media: str = "screen") -> None:
        self._driver.execute_cdp_cmd("Emulation.setEmulatedMedia", {"media": str(media)})

    def set_viewport_size(self, size: dict[str, int]) -> None:
        self._driver.execute_cdp_cmd(
            "Emulation.setDeviceMetricsOverride",
            {"width": int(size["width"]), "height": int(size["height"]), "deviceScaleFactor": 1, "mobile": False},
        )

    def goto(self, url: str, wait_until: str | None = None) -> None:
        self._driver.get(url)

    def evaluate(self, expression: str, arg: object = None) -> object:
        return self._driver.execute_async_script(
            f"const fn = {expression}; const cb = arguments[arguments.length - 1]; Promise.resolve(fn(arguments[0])).then(cb);",
            arg,
        )


def _get_playwright_page():
    global _PLAYWRIGHT, _BROWSER, _PAGE
    if _PAGE is not None and not _PAGE.is_closed():
        return _PAGE
    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError:
        _PAGE = _SeleniumPageAdapter(_get_selenium_driver())
        return _PAGE

    _PLAYWRIGHT = sync_playwright().start()
    launch_kwargs: dict[str, object] = {
        "headless": True,
        "args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
    }
    if Path("/usr/bin/chromium").exists():
        launch_kwargs["executable_path"] = "/usr/bin/chromium"
    _BROWSER = _PLAYWRIGHT.chromium.launch(**launch_kwargs)
    _PAGE = _BROWSER.new_page()
    atexit.register(_shutdown_playwright)
    return _PAGE


def run_node_script(node_script: str, app_dir: Path) -> subprocess.CompletedProcess[str]:
    """Execute a Node-style CommonJS test script via `node` or Headless Chromium V8."""
    node_bin = shutil.which("node")
    if node_bin and "vm.runInContext" not in node_script and "return (" not in node_script:
        return subprocess.run(
            [node_bin, "-e", node_script],
            env={**os.environ, "APP_DIR": str(app_dir)},
            capture_output=True,
            text=True,
            check=False,
        )

    files_map: dict[str, str] = {}
    for js_file in app_dir.rglob("*.js"):
        if ".git" in js_file.parts or ".wrangler" in js_file.parts or "node_modules" in js_file.parts:
            continue
        content = js_file.read_text(encoding="utf-8")
        files_map[str(js_file.resolve())] = content
        files_map[str(js_file)] = content
    if ".ts" in node_script or "vitest" in node_script:
        for ext in ("*.ts", "*.tsx"):
            for ts_file in app_dir.rglob(ext):
                if ts_file.name.endswith(".d.ts") or ".git" in ts_file.parts or ".wrangler" in ts_file.parts or "node_modules" in ts_file.parts:
                    continue
                transpiled = _transpile_ts_file(ts_file, app_dir)
                files_map[str(ts_file.resolve())] = transpiled
                files_map[str(ts_file)] = transpiled

    harness = r"""
    ([scriptSrc, appDir, filesMap]) => new Promise((done) => {
    const logs = [];
    const errs = [];
    const origLog = console.log;
    const origErr = console.error;
    console.log = (...args) => logs.push(args.map(a => typeof a === 'string' ? a : JSON.stringify(a)).join(' '));
    console.error = (...args) => errs.push(args.map(a => (a && a.stack) ? a.stack : String(a)).join(' '));

    class NodeRequest {
        constructor(input, init = {}) {
            this.url = typeof input === 'string' ? input : input.url;
            this.method = (init.method || (input && input.method) || 'GET').toUpperCase();
            this._body = init.body !== undefined ? init.body : (input && input._body !== undefined ? input._body : null);
            this.headers = new Headers();
            const rawHeaders = init.headers || (input && input.headers);
            this._customHeaders = new Map();
            if (rawHeaders) {
                const entries = rawHeaders instanceof Headers ? Array.from(rawHeaders.entries()) : Object.entries(rawHeaders);
                for (const [k, v] of entries) {
                    this._customHeaders.set(String(k).toLowerCase(), String(v));
                    try { this.headers.set(k, v); } catch (_) {}
                }
            }
            const origGet = this.headers.get.bind(this.headers);
            this.headers.get = (name) => {
                const low = String(name).toLowerCase();
                if (this._customHeaders.has(low)) return this._customHeaders.get(low);
                return origGet(name);
            };
        }
        async arrayBuffer() {
            if (!this._body) return new ArrayBuffer(0);
            return new TextEncoder().encode(String(this._body)).buffer;
        }
        async text() {
            return this._body ? String(this._body) : '';
        }
    }

    const assertFn = (cond, msg) => {
        if (!cond) throw new Error(msg || 'AssertionError: expected truthy value');
    };
    assertFn.strictEqual = (actual, expected, msg) => {
        if (actual !== expected) {
            throw new Error(msg || `AssertionError: expected ${JSON.stringify(actual)} === ${JSON.stringify(expected)}`);
        }
    };
    assertFn.deepStrictEqual = (actual, expected, msg) => {
        if (JSON.stringify(actual) !== JSON.stringify(expected)) {
            throw new Error(msg || `AssertionError: expected ${JSON.stringify(actual)} deepStrictEqual ${JSON.stringify(expected)}`);
        }
    };

    const pathMod = {
        join: (...parts) => parts.join('/').replace(/\/+/g, '/'),
        resolve: (...parts) => parts.join('/').replace(/\/+/g, '/'),
        dirname: (p) => String(p).split('/').slice(0, -1).join('/') || '/'
    };
    const resolveInFilesMap = (p, baseDir) => {
        const norm = (s) => {
            const out = [];
            for (const seg of String(s).split('/')) {
                if (!seg || seg === '.') continue;
                if (seg === '..') out.pop();
                else out.push(seg);
            }
            return '/' + out.join('/');
        };
        const raw = (String(p).startsWith('.') && baseDir) ? norm(baseDir + '/' + p) : (String(p).startsWith('/') ? norm(p) : p);
        for (const cand of [p, raw, raw + '.ts', raw + '.tsx', raw + '.js']) {
            if (cand in filesMap) return cand;
        }
        return p;
    };
    const fsMod = {
        readFileSync: (p) => {
            const resolved = resolveInFilesMap(p, appDir);
            if (!(resolved in filesMap)) throw new Error('ENOENT: ' + p);
            return filesMap[resolved];
        }
    };
    const vitestSuites = [];
    let currentSuiteTests = [];
    let currentBeforeEach = null;
    let currentAfterEach = null;
    const vitestMod = {
        describe: (name, fn) => {
            const prevTests = currentSuiteTests, prevBe = currentBeforeEach, prevAe = currentAfterEach;
            currentSuiteTests = [];
            fn();
            vitestSuites.push({ name, tests: currentSuiteTests });
            currentSuiteTests = prevTests; currentBeforeEach = prevBe; currentAfterEach = prevAe;
        },
        beforeEach: (fn) => { currentBeforeEach = fn; },
        afterEach: (fn) => { currentAfterEach = fn; },
        it: (name, fn) => {
            const be = currentBeforeEach, ae = currentAfterEach;
            currentSuiteTests.push({ name, fn: async () => { if (be) await be(); try { await fn(); } finally { if (ae) await ae(); } } });
        },
        expect: (actual) => ({
            toBe: (e) => { if (actual !== e) throw new Error(`Expected ${JSON.stringify(actual)} toBe ${JSON.stringify(e)}`); },
            toEqual: (e) => { if (JSON.stringify(actual) !== JSON.stringify(e)) throw new Error(`Expected ${JSON.stringify(actual)} toEqual ${JSON.stringify(e)}`); },
            toBeCloseTo: (e, p = 2) => { if (Math.abs(actual - e) >= Math.pow(10, -p) / 2) throw new Error(`Expected ${actual} toBeCloseTo ${e}`); },
            toContain: (e) => { if (!String(actual).includes(String(e)) && !(Array.isArray(actual) && actual.includes(e))) throw new Error(`Expected ${actual} toContain ${e}`); },
            toBeTruthy: () => { if (!actual) throw new Error(`Expected ${actual} toBeTruthy`); },
            toBeFalsy: () => { if (actual) throw new Error(`Expected ${actual} toBeFalsy`); },
            toHaveLength: (n) => { if (!actual || actual.length !== n) throw new Error(`Expected length ${n}`); },
            toBeGreaterThan: (n) => { if (!(actual > n)) throw new Error(`Expected ${actual} > ${n}`); },
        }),
        vi: { fn: (impl) => (...args) => (impl ? impl(...args) : undefined) }
    };
    vitestMod.test = vitestMod.it;
    globalThis.__runVitestSuites = async () => {
        let passed = 0;
        while (vitestSuites.length > 0) {
            const suite = vitestSuites.shift();
            for (const t of suite.tests) { await t.fn(); passed += 1; }
        }
        return passed;
    };
    const ensureMockRenderSlot = (w, doc) => {
        if (!w || typeof w !== 'object') return;
        if (!w.ReactDOM) {
            w.ReactDOM = { renderHtml: (el, s) => { if (el && typeof el === 'object') el.innerHTML = String(s ?? ''); } };
        }
        if (typeof w.renderSlot !== 'function') {
            w.renderSlot = (el, s) => {
                const d = doc || w.document;
                const target = typeof el === 'string' && d && typeof d.getElementById === 'function' ? d.getElementById(el) : el;
                if (target && typeof target === 'object') target.innerHTML = String(s ?? '');
            };
        }
    };
    const vmMod = {
        createContext: (sandbox) => {
            const ctx = sandbox || {};
            if (ctx.window) ensureMockRenderSlot(ctx.window, ctx.document);
            return ctx;
        },
        runInContext: (code, sandbox) => {
            const ctx = sandbox || {};
            if (ctx.window) ensureMockRenderSlot(ctx.window, ctx.document);
            let rewritten = String(code);
            if (!/^(?:var\s+renderSlot\s*=[\s\S]*?;\s*)?\(function\b/.test(rewritten.trimStart())) {
                const declRe = /(?:^|\n)(?:    )?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=/g;
                let m;
                while ((m = declRe.exec(rewritten)) !== null) {
                    if (!(m[1] in ctx)) ctx[m[1]] = undefined;
                }
                rewritten = rewritten.replace(/(^|\n)(    )?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=/g, '$1$2$3 =');
                const fnRe = /(?:^|\n)(?:    )?function\s+([A-Za-z_$][\w$]*)\s*\(/g;
                const fnNames = [];
                while ((m = fnRe.exec(rewritten)) !== null) {
                    if (!(m[1] in ctx)) ctx[m[1]] = undefined;
                    fnNames.push(m[1]);
                }
                if (fnNames.length) {
                    rewritten += '\n;' + fnNames.map(n => `__ctx.${n} = ${n};`).join(' ');
                }
            }
            const fn = new Function('__ctx', `with (__ctx) {\n${rewritten}\n}`);
            return fn(ctx);
        },
        runInNewContext: (code, sandbox) => {
            if (sandbox && sandbox.window) ensureMockRenderSlot(sandbox.window, sandbox.document);
            const keys = Object.keys(sandbox);
            const vals = keys.map(k => sandbox[k]);
            const fn = new Function(...keys, code);
            return fn(...vals);
        }
    };
    const procMod = {
        env: { APP_DIR: appDir },
        exit: (code) => { throw new Error('PROCESS_EXIT:' + code); }
    };

    const defaultStore = {};
    const defaultLocalStorage = {
        getItem: (k) => (k in defaultStore ? defaultStore[k] : null),
        setItem: (k, v) => { defaultStore[k] = String(v); },
        removeItem: (k) => { delete defaultStore[k]; }
    };
    const globalState = {
        localStorage: defaultLocalStorage,
        window: { localStorage: defaultLocalStorage },
        document: { getElementById: () => null, addEventListener: () => {}, querySelectorAll: () => [] },
        Request: NodeRequest
    };
    ensureMockRenderSlot(globalState.window, globalState.document);
    const globalProxy = new Proxy(globalState, {
        set(target, prop, value) {
            target[prop] = value;
            return true;
        },
        get(target, prop) {
            if (prop in target) return target[prop];
            return globalThis[prop];
        }
    });

    const dynamicDoc = new Proxy({}, {
        get(_, prop) {
            const d = globalState.document || (globalState.window && globalState.window.document) || {};
            const val = d[prop];
            return typeof val === 'function' ? val.bind(d) : val;
        },
        set(_, prop, value) {
            if (!globalState.document) globalState.document = {};
            globalState.document[prop] = value;
            return true;
        }
    });

    const modCache = {};
    const makeRequire = (baseDir) => (id) => {
        if (id === 'assert') return assertFn;
        if (id === 'path') return pathMod;
        if (id === 'fs') return fsMod;
        if (id === 'vm') return vmMod;
        if (id === 'vitest') return vitestMod;
        const resolved = resolveInFilesMap(id, baseDir);
        if (modCache[resolved]) return modCache[resolved].exports;
        const src = fsMod.readFileSync(resolved);
        const mod = { exports: {} };
        modCache[resolved] = mod;
        const win = globalState.window || {};
        ensureMockRenderSlot(win, dynamicDoc);
        const loc = globalState.localStorage || win.localStorage || defaultLocalStorage;
        const StorageCtor = globalState.Storage || class {};
        const CustomEventCtor = globalState.CustomEvent || globalThis.CustomEvent;
        const childDir = pathMod.dirname(resolved);
        const fn = new Function(
            'exports', 'require', 'module', 'window', 'localStorage', 'document', 'Storage', 'CustomEvent', 'Request', 'global',
            src
        );
        fn(mod.exports, makeRequire(childDir), mod, win, loc, dynamicDoc, StorageCtor, CustomEventCtor, NodeRequest, globalProxy);
        return mod.exports;
    };
    const requireFn = makeRequire(appDir);

    (async () => {
        try {
            const runner = new Function('require', 'process', 'global', 'Request', 'console', scriptSrc);
            await runner(requireFn, procMod, globalProxy, NodeRequest, console);
            if (vitestSuites.length > 0) {
                const passed = await globalThis.__runVitestSuites();
                logs.push(`VITEST_PASSED:${passed}`);
            }
            await new Promise(r => setTimeout(r, 120));
            if (errs.length > 0) {
                done({ returncode: 1, stdout: logs.join('\n'), stderr: errs.join('\n') });
            } else {
                done({ returncode: 0, stdout: logs.join('\n'), stderr: '' });
            }
        } catch (err) {
            done({ returncode: 1, stdout: logs.join('\n'), stderr: (err && err.stack) ? err.stack : String(err) });
        } finally {
            console.log = origLog;
            console.error = origErr;
        }
    })();
    })
    """
    page = _get_playwright_page()
    page.goto("about:blank")
    res = page.evaluate(harness, [node_script, str(app_dir), files_map])
    return subprocess.CompletedProcess(
        args=["node", "-e", node_script],
        returncode=int(res.get("returncode", 1)),
        stdout=str(res.get("stdout", "")),
        stderr=str(res.get("stderr", "")),
    )
