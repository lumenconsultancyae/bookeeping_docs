"""Playwright-compatible Headless Chromium browser shim backed by Selenium when `playwright` is not installed."""

from __future__ import annotations

import mimetypes
from pathlib import Path
import time

from features.support_server import BookkeepingRequestHandler
from tests.js_runner import _get_selenium_driver

try:
    from playwright.sync_api import sync_playwright as _real_sync_playwright
except ModuleNotFoundError:
    _real_sync_playwright = None

_RESOLVE_CHAIN_JS = """
const matchSelectorWithPseudo = (root, rawSel) => {
    let sel = String(rawSel || '').trim();
    let hasTextFilter = null;
    let hasChildSel = null;
    const textMatch = sel.match(/^(.*):has-text\\("([^"]+)"\\)(.*)$/) || sel.match(/^(.*):has-text\\('([^']+)'\\)(.*)$/);
    if (textMatch) {
        sel = (textMatch[1] + textMatch[3]).trim() || '*';
        hasTextFilter = textMatch[2];
    }
    const hasMatch = sel.match(/^(.*):has\\(([^)]+)\\)(.*)$/);
    if (hasMatch) {
        sel = (hasMatch[1] + hasMatch[3]).trim() || '*';
        hasChildSel = hasMatch[2].trim();
    }
    const candidates = Array.from(root.querySelectorAll(sel));
    return candidates.filter((el) => {
        if (hasTextFilter && !String(el.innerText ?? el.textContent ?? '').includes(hasTextFilter)) return false;
        if (hasChildSel && !el.querySelector(hasChildSel)) return false;
        return true;
    });
};
const resolveChain = (chain) => {
    let nodes = [document];
    for (const step of chain) {
        const [sel, hasText, nthIdx, hasChildChain] = step;
        const next = [];
        for (const root of nodes) {
            for (const el of matchSelectorWithPseudo(root, sel)) {
                if (hasText && !String(el.innerText ?? el.textContent ?? '').includes(hasText)) continue;
                if (hasChildChain && hasChildChain.length > 0) {
                    let childNodes = [el];
                    for (const cStep of hasChildChain) {
                        const [cSel, cText] = cStep;
                        const cNext = [];
                        for (const cRoot of childNodes) {
                            for (const cEl of matchSelectorWithPseudo(cRoot, cSel)) {
                                if (!cText || String(cEl.innerText ?? cEl.textContent ?? '').includes(cText)) cNext.push(cEl);
                            }
                        }
                        childNodes = cNext;
                    }
                    if (childNodes.length === 0) continue;
                }
                next.push(el);
            }
        }
        nodes = (nthIdx !== null && nthIdx !== undefined) ? (next[nthIdx] ? [next[nthIdx]] : []) : next;
    }
    return nodes;
};
"""


class _ShimLocator:
    def __init__(self, page: _ShimPage, chain: list[list[object]]) -> None:
        self._page = page
        self._chain = chain

    @property
    def first(self) -> _ShimLocator:
        return self.nth(0)

    def nth(self, index: int) -> _ShimLocator:
        updated = [list(s) for s in self._chain]
        if updated:
            updated[-1][2] = int(index)
        return _ShimLocator(self._page, updated)

    def filter(self, *, has: _ShimLocator | None = None, has_text: str | None = None) -> _ShimLocator:
        updated = [list(s) for s in self._chain]
        if updated:
            if has_text:
                updated[-1][1] = has_text
            if has is not None:
                updated[-1][3] = has._chain
        return _ShimLocator(self._page, updated)

    def locator(self, selector: str, *, has_text: str | None = None) -> _ShimLocator:
        return _ShimLocator(self._page, [*self._chain, [selector, has_text, None, None]])

    def count(self) -> int:
        return int(self._page.evaluate(f"(chain) => {{ {_RESOLVE_CHAIN_JS} return resolveChain(chain).length; }}", self._chain) or 0)

    def is_visible(self) -> bool:
        return bool(
            self._page.evaluate(
                f"(chain) => {{ {_RESOLVE_CHAIN_JS} const el = resolveChain(chain)[0]; if (!el) return false; const s = getComputedStyle(el); return s.display !== 'none' && s.visibility !== 'hidden' && (el.offsetWidth > 0 || el.offsetHeight > 0 || el.getClientRects().length > 0); }}",
                self._chain,
            )
        )

    def click(self, *, modifiers: list[str] | None = None, force: bool = False) -> None:
        ctrl = bool(modifiers and ("Control" in modifiers or "Meta" in modifiers))
        self._page.evaluate(
            f"([chain, ctrl]) => {{ {_RESOLVE_CHAIN_JS} const el = resolveChain(chain)[0]; if (!el) throw new Error('Element not found: ' + JSON.stringify(chain)); el.scrollIntoView({{ block: 'center', inline: 'nearest' }}); if (ctrl) {{ const evt = new MouseEvent('click', {{ bubbles: true, cancelable: true, ctrlKey: true, metaKey: true }}); el.dispatchEvent(evt); if (!evt.defaultPrevented && el.tagName === 'A' && el.href) window.open(el.href, '_blank'); }} else {{ el.click(); }} }}",
            [self._chain, ctrl],
        )

    def fill(self, value: str) -> None:
        self._page.evaluate(
            f"([chain, val]) => {{ {_RESOLVE_CHAIN_JS} const el = resolveChain(chain)[0]; if (!el) throw new Error('Element not found: ' + JSON.stringify(chain)); const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : (el instanceof HTMLSelectElement ? HTMLSelectElement.prototype : HTMLInputElement.prototype); const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set; if (setter) setter.call(el, String(val)); else el.value = String(val); el.dispatchEvent(new Event('input', {{ bubbles: true }})); el.dispatchEvent(new Event('change', {{ bubbles: true }})); }}",
            [self._chain, str(value)],
        )

    def select_option(self, value: str) -> None:
        self._page.evaluate(
            f"([chain, val]) => {{ {_RESOLVE_CHAIN_JS} const el = resolveChain(chain)[0]; if (!el) throw new Error('Element not found: ' + JSON.stringify(chain)); const setter = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value')?.set; if (setter) setter.call(el, String(val)); else el.value = String(val); el.dispatchEvent(new Event('input', {{ bubbles: true }})); el.dispatchEvent(new Event('change', {{ bubbles: true }})); }}",
            [self._chain, str(value)],
        )

    def inner_text(self) -> str:
        return str(self._page.evaluate(f"(chain) => {{ {_RESOLVE_CHAIN_JS} const el = resolveChain(chain)[0]; return el ? (el.innerText ?? el.textContent ?? '') : ''; }}", self._chain) or "")

    def all_inner_texts(self) -> list[str]:
        res = self._page.evaluate(f"(chain) => {{ {_RESOLVE_CHAIN_JS} return resolveChain(chain).map((el) => String(el.innerText ?? el.textContent ?? '')); }}", self._chain)
        return list(res or [])

    def input_value(self) -> str:
        return str(self._page.evaluate(f"(chain) => {{ {_RESOLVE_CHAIN_JS} const el = resolveChain(chain)[0]; return el ? String(el.value ?? '') : ''; }}", self._chain) or "")

    def get_attribute(self, name: str) -> str | None:
        val = self._page.evaluate(f"([chain, attr]) => {{ {_RESOLVE_CHAIN_JS} const el = resolveChain(chain)[0]; return el ? el.getAttribute(attr) : null; }}", [self._chain, name])
        return str(val) if val is not None else None

    def set_input_files(self, files: object) -> None:
        items = files if isinstance(files, list) else [files]
        payloads: list[dict[str, object]] = []
        for item in items:
            if isinstance(item, dict):
                buf = item.get("buffer") or b""
                raw_bytes = list(buf) if isinstance(buf, (bytes, bytearray)) else list(str(buf).encode("utf-8"))
                payloads.append({"name": str(item.get("name") or "file.bin"), "mime": str(item.get("mimeType") or "application/octet-stream"), "bytes": raw_bytes})
            else:
                p = Path(str(item))
                mime, _ = mimetypes.guess_type(p.name)
                payloads.append({"name": p.name, "mime": mime or "application/octet-stream", "bytes": list(p.read_bytes())})
        self._page.evaluate(
            f"([chain, files]) => {{ {_RESOLVE_CHAIN_JS} const el = resolveChain(chain)[0]; if (!el) throw new Error('File input not found: ' + JSON.stringify(chain)); const dt = new DataTransfer(); for (const f of files) {{ dt.items.add(new File([new Uint8Array(f.bytes)], f.name, {{ type: f.mime }})); }} el.files = dt.files; el.dispatchEvent(new Event('change', {{ bubbles: true }})); }}",
            [self._chain, payloads],
        )

    def screenshot(self, *, path: str, timeout: int = 10000) -> None:
        self._page.screenshot(path=path, timeout=timeout)


class _ShimPage:
    def __init__(self, driver, window_handle: str | None = None) -> None:
        self._driver = driver
        self._handle = window_handle or driver.current_window_handle

    def _activate(self) -> None:
        if self._handle in self._driver.window_handles and self._driver.current_window_handle != self._handle:
            self._driver.switch_to.window(self._handle)

    @property
    def url(self) -> str:
        self._activate()
        return str(self._driver.current_url or "")

    def on(self, _event: str, _handler: object) -> None:
        pass

    def goto(self, url: str, wait_until: str | None = None) -> None:
        self._activate()
        self._driver.get(url)

    def evaluate(self, expression: str, arg: object = None) -> object:
        self._activate()
        return self._driver.execute_async_script(
            f"const fn = {expression}; const cb = arguments[arguments.length - 1]; Promise.resolve(fn(arguments[0])).then(cb);",
            arg,
        )

    def wait_for_function(self, expression: str, timeout: int = 10000) -> None:
        deadline = time.time() + (timeout / 1000.0)
        while time.time() < deadline:
            try:
                if self.evaluate(expression):
                    return
            except Exception:
                pass
            time.sleep(0.05)
        raise AssertionError(f"Timeout waiting for function: {expression}")

    def wait_for_selector(self, selector: str, timeout: int = 5000) -> None:
        deadline = time.time() + (timeout / 1000.0)
        while time.time() < deadline:
            if self.locator(selector).count() > 0:
                return
            time.sleep(0.05)
        raise AssertionError(f"Timeout waiting for selector: {selector}")

    def wait_for_timeout(self, ms: int) -> None:
        time.sleep(max(ms, 0) / 1000.0)

    def locator(self, selector: str, *, has_text: str | None = None) -> _ShimLocator:
        return _ShimLocator(self, [[selector, has_text, None, None]])

    def fill(self, selector: str, value: str) -> None:
        self.locator(selector).fill(value)

    def click(self, selector: str) -> None:
        self.locator(selector).click()

    def select_option(self, selector: str, value: str) -> None:
        self.locator(selector).select_option(value)

    def input_value(self, selector: str) -> str:
        return self.locator(selector).input_value()

    def dispatch_event(self, selector: str, event_type: str) -> None:
        self.evaluate(
            f"([sel, ev]) => {{ const el = document.querySelector(sel); if (el) el.dispatchEvent(new Event(ev, {{ bubbles: true }})); }}",
            [selector, event_type],
        )

    def set_input_files(self, selector: str, files: object) -> None:
        self.locator(selector).set_input_files(files)

    def screenshot(self, *, path: str, full_page: bool = False, timeout: int = 10000) -> None:
        self._activate()
        self._driver.save_screenshot(str(path))

    def close(self) -> None:
        handles = list(self._driver.window_handles)
        if len(handles) > 1 and self._handle in handles:
            self._driver.switch_to.window(self._handle)
            self._driver.close()
            self._driver.switch_to.window(self._driver.window_handles[0])


class _ExpectPageContext:
    def __init__(self, driver) -> None:
        self._driver = driver
        self._before: set[str] = set()
        self.value: _ShimPage | None = None

    def __enter__(self) -> _ExpectPageContext:
        self._before = set(self._driver.window_handles)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is not None:
            return
        deadline = time.time() + 5.0
        while time.time() < deadline:
            diff = [h for h in self._driver.window_handles if h not in self._before]
            if diff:
                self.value = _ShimPage(self._driver, diff[-1])
                return
            time.sleep(0.05)
        raise AssertionError("Expected a new browser tab/page to open, but window_handles did not increase")


class _ShimContext:
    def __init__(self, driver, viewport: dict[str, int] | None = None) -> None:
        self._driver = driver
        if viewport:
            driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", {"width": int(viewport["width"]), "height": int(viewport["height"]), "deviceScaleFactor": 1, "mobile": False})

    @property
    def pages(self) -> list[_ShimPage]:
        return [_ShimPage(self._driver, h) for h in self._driver.window_handles]

    def route(self, _pattern: str, handler: object) -> None:
        BookkeepingRequestHandler.custom_api_handler = handler

    def new_page(self) -> _ShimPage:
        return _ShimPage(self._driver, self._driver.window_handles[0])

    def expect_page(self) -> _ExpectPageContext:
        return _ExpectPageContext(self._driver)

    def close(self) -> None:
        BookkeepingRequestHandler.custom_api_handler = None


class _ShimBrowser:
    def __init__(self, driver) -> None:
        self._driver = driver

    def new_context(self, viewport: dict[str, int] | None = None) -> _ShimContext:
        while len(self._driver.window_handles) > 1:
            self._driver.switch_to.window(self._driver.window_handles[-1])
            self._driver.close()
        self._driver.switch_to.window(self._driver.window_handles[0])
        return _ShimContext(self._driver, viewport=viewport)

    def close(self) -> None:
        BookkeepingRequestHandler.custom_api_handler = None


class _ShimPlaywright:
    class _Chromium:
        @staticmethod
        def launch(**_kwargs) -> _ShimBrowser:
            return _ShimBrowser(_get_selenium_driver())

    chromium = _Chromium()

    def __enter__(self) -> _ShimPlaywright:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        BookkeepingRequestHandler.custom_api_handler = None


def sync_playwright():
    """Return official Playwright context manager if installed, or Headless Chromium Selenium shim."""
    if _real_sync_playwright is not None:
        return _real_sync_playwright()
    return _ShimPlaywright()
