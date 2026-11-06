"""Portable JavaScript behavioral test runner using Node.js when available or Headless Chromium V8 fallback."""

from __future__ import annotations

import atexit
import os
from pathlib import Path
import shutil
import subprocess

_DRIVER = None


def _get_chromium_driver():
    global _DRIVER
    if _DRIVER is not None:
        return _DRIVER
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service

    options = Options()
    if Path("/usr/bin/chromium").exists():
        options.binary_location = "/usr/bin/chromium"
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    service = Service(executable_path="/usr/bin/chromedriver") if Path("/usr/bin/chromedriver").exists() else Service()
    _DRIVER = webdriver.Chrome(service=service, options=options)
    atexit.register(lambda: _DRIVER.quit() if _DRIVER else None)
    return _DRIVER


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

    driver = _get_chromium_driver()
    driver.get("about:blank")
    harness = r"""
    const [scriptSrc, appDir, filesMap, done] = arguments;
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
    """
    res = driver.execute_async_script(harness, node_script, str(app_dir), files_map)
    return subprocess.CompletedProcess(
        args=["node", "-e", node_script],
        returncode=int(res.get("returncode", 1)),
        stdout=str(res.get("stdout", "")),
        stderr=str(res.get("stderr", "")),
    )
