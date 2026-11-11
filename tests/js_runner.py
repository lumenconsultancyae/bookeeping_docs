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
    def __init__(self, page: _SeleniumPageAdapter, selector: str) -> None:
        self._page = page
        self._selector = selector

    @property
    def first(self) -> _SeleniumLocatorAdapter:
        return self

    def count(self) -> int:
        return int(self._page.evaluate("(sel) => document.querySelectorAll(sel).length", self._selector) or 0)

    def is_visible(self) -> bool:
        return bool(
            self._page.evaluate(
                "(sel) => { const el = document.querySelector(sel); if (!el) return false; const s = getComputedStyle(el); return s.display !== 'none' && s.visibility !== 'hidden' && (el.offsetWidth > 0 || el.offsetHeight > 0 || el.getClientRects().length > 0); }",
                self._selector,
            )
        )

    def inner_text(self) -> str:
        return str(self._page.evaluate("(sel) => { const el = document.querySelector(sel); return el ? (el.innerText ?? el.textContent ?? '') : ''; }", self._selector) or "")

    def inner_html(self) -> str:
        return str(self._page.evaluate("(sel) => { const el = document.querySelector(sel); return el ? (el.innerHTML ?? '') : ''; }", self._selector) or "")

    def input_value(self) -> str:
        return str(self._page.evaluate("(sel) => { const el = document.querySelector(sel); return el ? String(el.value ?? '') : ''; }", self._selector) or "")

    def is_checked(self) -> bool:
        return bool(self._page.evaluate("(sel) => { const el = document.querySelector(sel); return Boolean(el && el.checked); }", self._selector))

    def get_attribute(self, name: str) -> str | None:
        val = self._page.evaluate("([sel, attr]) => { const el = document.querySelector(sel); return el ? el.getAttribute(attr) : null; }", [self._selector, name])
        return str(val) if val is not None else None

    def evaluate(self, expression: str, arg: object = None) -> object:
        return self._page.evaluate(
            f"([sel, arg]) => {{ const el = document.querySelector(sel); if (!el) throw new Error('Element not found: ' + sel); const fn = {expression}; return fn(el, arg); }}",
            [self._selector, arg],
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

    def locator(self, selector: str) -> _SeleniumLocatorAdapter:
        return _SeleniumLocatorAdapter(self, selector)

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
    if node_bin:
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
        files_map[str(js_file.resolve())] = js_file.read_text(encoding="utf-8")
        files_map[str(js_file)] = files_map[str(js_file.resolve())]

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
        join: (...parts) => parts.join('/').replace(/\/+/g, '/')
    };
    const fsMod = {
        readFileSync: (p) => {
            if (!(p in filesMap)) throw new Error('ENOENT: ' + p);
            return filesMap[p];
        }
    };
    const vmMod = {
        createContext: (sandbox) => sandbox || {},
        runInContext: (code, sandbox) => {
            const ctx = sandbox || {};
            let rewritten = String(code);
            if (!rewritten.trimStart().startsWith('(function')) {
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
    const requireFn = (id) => {
        if (id === 'assert') return assertFn;
        if (id === 'path') return pathMod;
        if (id === 'fs') return fsMod;
        if (id === 'vm') return vmMod;
        if (modCache[id]) return modCache[id].exports;
        const src = fsMod.readFileSync(id);
        const mod = { exports: {} };
        modCache[id] = mod;
        const win = globalState.window || {};
        const loc = globalState.localStorage || win.localStorage || defaultLocalStorage;
        const StorageCtor = globalState.Storage || class {};
        const CustomEventCtor = globalState.CustomEvent || globalThis.CustomEvent;
        const fn = new Function(
            'exports', 'require', 'module', 'window', 'localStorage', 'document', 'Storage', 'CustomEvent', 'Request', 'global',
            src
        );
        fn(mod.exports, requireFn, mod, win, loc, dynamicDoc, StorageCtor, CustomEventCtor, NodeRequest, globalProxy);
        return mod.exports;
    };

    (async () => {
        try {
            const runner = new Function('require', 'process', 'global', 'Request', 'console', scriptSrc);
            await runner(requireFn, procMod, globalProxy, NodeRequest, console);
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
