"""Real-DOM component harness for the bookkeeping-tool UI kit modules.

Loads the vanilla-JS modules (`ui-feedback.js`, `ui-forms.js`, `ui-tables.js`, `ui-layout.js`)
into a blank headless-Chromium page with a minimal fixture DOM, so component behaviour
(focus, ARIA, MutationObserver, constraint validation) is exercised against a real browser
engine instead of a hand-written fake DOM. Reuses the shared driver from `tests/js_runner.py`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tests.js_runner import _get_playwright_page

APP_DIR = Path(__file__).resolve().parent.parent.parent / "bookkeeping-tool"
UI_MODULES = ("ui-feedback.js", "ui-forms.js", "ui-tables.js", "ui-layout.js")


class DomComponentHarness:
    """Mount a fixture DOM plus UI-kit modules in headless Chromium via Playwright and run async JS probes."""

    def __init__(self, width: int = 1280, height: int = 900) -> None:
        self.page = _get_playwright_page()
        self.page.set_viewport_size({"width": width, "height": height})

    def mount(self, body_html: str, modules: tuple[str, ...] = UI_MODULES, css: str = "") -> None:
        """Reset the page, inject `body_html`, optional CSS, and the requested module sources in order."""
        self.page.goto("about:blank")
        sources = [(APP_DIR / name).read_text(encoding="utf-8") for name in modules]
        kit_css = (APP_DIR / "ui-kit.css").read_text(encoding="utf-8")
        self.page.evaluate(
            """
            ([html, sources, css]) => {
                document.documentElement.innerHTML = '<head></head><body></body>';
                const style = document.createElement('style');
                style.textContent = css;
                document.head.appendChild(style);
                document.body.innerHTML = html;
                try { window.localStorage.getItem('probe'); } catch (_) {
                    /* about:blank has an opaque origin; provide an in-memory Storage for the modules under test. */
                    const store = new Map();
                    Object.defineProperty(window, 'localStorage', { configurable: true, value: {
                        getItem: (k) => (store.has(k) ? store.get(k) : null), setItem: (k, v) => store.set(k, String(v)),
                        removeItem: (k) => store.delete(k), clear: () => store.clear() } });
                }
                for (const src of sources) { (0, eval)(src); }
            }
            """,
            [body_html, sources, kit_css + "\n" + css],
        )

    def run(self, script: str, *args: Any) -> Any:
        """Execute an async probe; the script must call `done(value)` (last argument)."""
        wrapped = (
            "([__args]) => new Promise((done) => {"
            "const args = __args;"
            "const tick = (ms = 0) => new Promise((r) => setTimeout(r, ms));"
            "(async () => {" + script + "})().catch((e) => done({ __error: String(e && e.stack || e) }));"
            "})"
        )
        result = self.page.evaluate(wrapped, [list(args)])
        if isinstance(result, dict) and "__error" in result:
            raise AssertionError(result["__error"])
        return result
