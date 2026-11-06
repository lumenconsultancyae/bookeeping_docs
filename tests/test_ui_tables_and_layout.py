"""Unit & component tests for paginated data tables and the responsive drawer layout.

User stories covered:
1. As a bookkeeper browsing a long list (ledger, customers, COA) I page through it inside its
   card instead of scrolling the whole page, choose rows per page, and search (`ui-tables.js`).
2. After saving a record I immediately see it highlighted, even when it lands on another page.
3. On a tablet or phone the navigation is an off-canvas drawer that never pushes the
   workspace down the page (`ui-layout.js` + `ui-kit.css`).
"""

from __future__ import annotations

import re
import unittest

from tests.dom_harness import APP_DIR, DomComponentHarness

LIST_TBODIES = (
    "historyBody", "dirCustBody", "dirSupBody", "dirEmpBody", "inventoryDirectoryBody", "stockLedgerBody",
    "coaBody", "chequeRegistryBody", "quotesHistoryBody", "poHistoryBody", "creditNotesHistoryBody",
    "expListBody", "auditLogBody", "accrualsDirectoryBody", "assetsDirectoryBody", "recurringBody",
    "bankRulesBody", "bankFeedsBody", "bankDashboardBody", "currencyRatesBody",
)


def _table_fixture(rows: int, searchable: bool = True) -> str:
    body = "".join(
        f"<tr><td>Customer {i:02d} Trading LLC</td><td>ap{i}@client.ae</td><td>{100000000000000 + i}</td></tr>"
        for i in range(1, rows + 1)
    )
    search_attr = ' data-searchable="Search customers…"' if searchable else ""
    return (
        '<div class="card"><div class="table-container"><table class="erp-table"><thead><tr>'
        "<th>Name</th><th>Email</th><th>TRN</th></tr></thead>"
        f'<tbody id="dirCustBody" data-paginate="10" data-paginate-label="customers"{search_attr}>{body}</tbody>'
        "</table></div></div>"
    )


SNAPSHOT_JS = """
    const tb = document.getElementById('dirCustBody');
    const shown = Array.from(tb.rows).filter((r) => getComputedStyle(r).display !== 'none');
    const pager = document.querySelector('.table-pager');
    return {
        shown: shown.length, first: shown[0] ? shown[0].cells[0].textContent : null,
        summary: pager.querySelector('.table-pager__summary').textContent, pagerHidden: pager.hidden,
        current: (pager.querySelector('[aria-current="page"]') || {}).textContent || null,
        pages: Array.from(pager.querySelectorAll('.table-pager__pages > *')).map((b) => b.textContent),
        prevDisabled: pager.querySelector('[aria-label="Previous page"]').disabled,
        nextDisabled: pager.querySelector('[aria-label="Next page"]').disabled,
        searchHidden: document.querySelector('.table-search') ? document.querySelector('.table-search').hidden : null,
    };
"""


class ListTemplatesOptIntoPaginationTests(unittest.TestCase):
    """Static guardrails on the view templates."""

    def _views(self) -> str:
        return "\n".join(p.read_text(encoding="utf-8") for p in sorted(APP_DIR.glob("views-*.js")))

    def test_every_list_table_is_paginated_with_a_human_label(self) -> None:
        views = self._views()
        for tbody_id in LIST_TBODIES:
            match = re.search(rf'<tbody id="{tbody_id}"([^>]*)>', views)
            self.assertIsNotNone(match, tbody_id)
            self.assertIn('data-paginate="10"', match.group(1), tbody_id)
            self.assertIn("data-paginate-label=", match.group(1), tbody_id)

    def test_list_tables_drop_adhoc_inner_scroll_boxes_and_contact_forms_use_grid_and_constraints(self) -> None:
        views = self._views()
        self.assertNotIn('class="table-container" style="max-height: 400px; overflow-y: auto;"', views)
        self.assertIn('<form id="addCustomerForm" class="form-grid">', views)
        self.assertIn('<form id="addSupplierForm" class="form-grid">', views)
        for trn_id in ("dirCustTrn", "dirSupTrn"):
            tag = re.search(rf'<input[^>]*id="{trn_id}"[^>]*>', views).group(0)
            self.assertIn('pattern="[0-9]{15}"', tag)
            self.assertIn("data-error-pattern=", tag)
        for amount_id in ("recAmount", "accrualAmount", "chequeAmount"):
            tag = re.search(rf'<input[^>]*id="{amount_id}"[^>]*>', views).group(0)
            self.assertIn('min="0.01"', tag, amount_id)

    def test_table_cells_no_longer_break_words_mid_token(self) -> None:
        kit = (APP_DIR / "ui-kit.css").read_text(encoding="utf-8")
        self.assertIn(".erp-table td, .data-table td, .table td { overflow-wrap: break-word; word-break: normal; }", kit)


class PaginatedTableComponentTests(unittest.TestCase):
    """`ui-tables.js` behaviour against a real DOM and MutationObserver."""

    def setUp(self) -> None:
        self.dom = DomComponentHarness()

    def _mount(self, rows: int, searchable: bool = True) -> None:
        self.dom.mount(_table_fixture(rows, searchable), modules=("ui-tables.js",))

    def snapshot(self) -> dict:
        return self.dom.run(f"await tick(20); done((() => {{ {SNAPSHOT_JS} }})());")

    def test_long_list_shows_first_page_with_summary_and_numbered_pager(self) -> None:
        self._mount(57)
        snap = self.snapshot()
        self.assertEqual(snap["shown"], 10)
        self.assertEqual(snap["first"], "Customer 01 Trading LLC")
        self.assertEqual(snap["summary"], "Showing 1–10 of 57")
        self.assertFalse(snap["pagerHidden"])
        self.assertEqual(snap["current"], "1")
        self.assertEqual(snap["pages"], ["‹", "1", "2", "3", "4", "5", "6", "›"])
        self.assertTrue(snap["prevDisabled"])
        self.assertFalse(snap["nextDisabled"])

    def test_next_page_and_rows_per_page_change_visible_rows(self) -> None:
        self._mount(57)
        self.dom.run("document.querySelector('[aria-label=\"Next page\"]').click(); done(true);")
        page2 = self.snapshot()
        self.assertEqual((page2["first"], page2["summary"], page2["current"]),
                         ("Customer 11 Trading LLC", "Showing 11–20 of 57", "2"))
        self.dom.run("""
            const sel = document.querySelector('.table-pager select');
            sel.value = '50'; sel.dispatchEvent(new Event('change', { bubbles: true })); done(true);
        """)
        big = self.snapshot()
        self.assertEqual((big["shown"], big["summary"], big["current"]), (50, "Showing 1–50 of 57", "1"))
        stored = self.dom.run("done(localStorage.getItem('lumen_table_page_size:dirCustBody'));")
        self.assertEqual(stored, "50")

    def test_search_filters_rows_and_resets_to_first_page(self) -> None:
        self._mount(57)
        self.dom.run("""
            document.querySelector('[aria-label="Page 3"]').click();
            const input = document.querySelector('.table-search input');
            input.value = 'customer 4'; input.dispatchEvent(new Event('input', { bubbles: true })); done(true);
        """)
        snap = self.snapshot()
        self.assertEqual(snap["summary"], "Showing 1–10 of 10")
        self.assertEqual(snap["first"], "Customer 40 Trading LLC")
        self.dom.run("""
            const input = document.querySelector('.table-search input');
            input.value = 'zzz'; input.dispatchEvent(new Event('input', { bubbles: true })); done(true);
        """)
        self.assertEqual(self.snapshot()["summary"], "No matching rows")

    def test_external_inline_filters_are_respected(self) -> None:
        self._mount(30, searchable=False)
        self.dom.run("""
            Array.from(document.getElementById('dirCustBody').rows).forEach((r, i) => { if (i % 2) r.style.display = 'none'; });
            done(true);
        """)
        snap = self.snapshot()
        self.assertEqual(snap["summary"], "Showing 1–10 of 15")
        self.assertEqual(snap["shown"], 10)

    def test_rerender_with_new_row_jumps_to_its_page_and_highlights_it(self) -> None:
        self._mount(25)
        result = self.dom.run("""
            const tb = document.getElementById('dirCustBody');
            const rows = Array.from(tb.rows).map((r) => r.outerHTML);
            rows.push('<tr><td>Zeta Newly Added LLC</td><td>z@z.ae</td><td>100999999999903</td></tr>');
            tb.innerHTML = rows.join('');
            await tick(40);
            const added = Array.from(tb.rows).find((r) => r.cells[0].textContent.startsWith('Zeta'));
            done({ visible: getComputedStyle(added).display !== 'none', highlighted: added.classList.contains('row-highlight'),
                   current: document.querySelector('[aria-current="page"]').textContent });
        """)
        self.assertEqual(result, {"visible": True, "highlighted": True, "current": "3"})

    def test_first_lazy_render_does_not_flash_but_first_row_saved_from_a_form_does(self) -> None:
        self.dom.mount(_table_fixture(0) + '<form id="f"><button type="submit">Save</button></form>',
                       modules=("ui-tables.js",))
        result = self.dom.run("""
            const tb = document.getElementById('dirCustBody');
            const row = (n) => `<tr><td>${n}</td><td>-</td><td>-</td></tr>`;
            tb.innerHTML = row('Lazy Loaded LLC');
            await tick(30);
            const lazyFlash = tb.rows[0].classList.contains('row-highlight');
            tb.innerHTML = '';
            await tick(30);
            const form = document.getElementById('f');
            form.addEventListener('submit', (e) => { e.preventDefault(); tb.innerHTML = row('First Saved LLC'); });
            form.requestSubmit();
            await tick(30);
            done({ lazyFlash, savedFlash: tb.rows[0].classList.contains('row-highlight') });
        """)
        self.assertEqual(result, {"lazyFlash": False, "savedFlash": True})

    def test_short_lists_hide_pager_and_search_and_placeholder_rows_are_never_paged(self) -> None:
        self._mount(4)
        snap = self.snapshot()
        self.assertEqual(snap["shown"], 4)
        self.assertTrue(snap["pagerHidden"])
        self.assertTrue(snap["searchHidden"])
        self.dom.run("""
            document.getElementById('dirCustBody').innerHTML = '<tr><td colspan="3">No customers yet.</td></tr>';
            done(true);
        """)
        empty = self.snapshot()
        self.assertEqual((empty["shown"], empty["summary"], empty["pagerHidden"]), (1, "No rows", True))

    def test_page_window_collapses_long_ranges_with_ellipses(self) -> None:
        self._mount(1)
        windows = self.dom.run(
            "const w = window.LumenTables.pageWindow; done([w(1, 5), w(5, 10), w(10, 10)]);")
        self.assertEqual(windows[0], [1, 2, 3, 4, 5])
        self.assertEqual(windows[1], [1, "…", 4, 5, 6, "…", 10])
        self.assertEqual(windows[2], [1, "…", 7, 8, 9, 10])


LAYOUT_FIXTURE = """
<div class="app-layout">
  <aside class="sidebar"><nav class="sidebar-nav">
    <a href="#" class="nav-item active" data-target="view-dashboard">Dashboard</a>
    <a href="#" class="nav-item" data-target="view-ledger">General Ledger</a>
  </nav></aside>
  <main class="main-content"><header class="topbar"><div class="topbar-left">
    <button type="button" id="btnSidebarToggle" aria-label="Toggle Sidebar">=</button><h1 id="pageTitle">Dashboard</h1>
  </div></header><div class="dashboard-content"></div></main>
</div>
"""
DESKTOP_COLLAPSE_HANDLER = """
document.getElementById('btnSidebarToggle').addEventListener('click', () => {
    window.__collapsed = document.body.classList.toggle('sidebar-collapsed');
});
"""


class ResponsiveDrawerComponentTests(unittest.TestCase):
    """`ui-layout.js` turns the sidebar into an accessible drawer below 960px."""

    def _mount(self, width: int) -> DomComponentHarness:
        dom = DomComponentHarness(width=width, height=900)
        dom.mount(LAYOUT_FIXTURE, modules=("ui-layout.js",))
        dom.run(DESKTOP_COLLAPSE_HANDLER + "done(true);")
        return dom

    def test_mobile_toggle_opens_drawer_and_backdrop_escape_or_navigation_close_it(self) -> None:
        dom = self._mount(700)
        result = dom.run("""
            const toggle = document.getElementById('btnSidebarToggle');
            const out = { controls: toggle.getAttribute('aria-controls') };
            toggle.click(); await tick(20);
            out.open = document.body.classList.contains('sidebar-open');
            out.expanded = toggle.getAttribute('aria-expanded');
            out.label = toggle.getAttribute('aria-label');
            out.desktopHandlerRan = window.__collapsed === true;
            document.querySelector('.sidebar-backdrop').click(); await tick(20);
            out.closedByBackdrop = !document.body.classList.contains('sidebar-open');
            toggle.click(); await tick(10);
            document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
            out.closedByEscape = !document.body.classList.contains('sidebar-open');
            out.focusBack = document.activeElement === toggle;
            toggle.click(); await tick(10);
            document.querySelector('[data-target="view-ledger"]').click();
            out.closedByNav = !document.body.classList.contains('sidebar-open');
            done(out);
        """)
        self.assertEqual(result["controls"], "appSidebar")
        self.assertTrue(result["open"])
        self.assertEqual(result["expanded"], "true")
        self.assertEqual(result["label"], "Close navigation menu")
        self.assertFalse(result["desktopHandlerRan"], "Drawer mode must not trigger the desktop collapse rail")
        self.assertTrue(result["closedByBackdrop"])
        self.assertTrue(result["closedByEscape"])
        self.assertTrue(result["focusBack"])
        self.assertTrue(result["closedByNav"])

    def test_desktop_toggle_keeps_the_collapse_rail_behaviour(self) -> None:
        dom = self._mount(1300)
        result = dom.run("""
            document.getElementById('btnSidebarToggle').click(); await tick(10);
            done({ collapsed: window.__collapsed === true, drawer: document.body.classList.contains('sidebar-open') });
        """)
        self.assertEqual(result, {"collapsed": True, "drawer": False})


if __name__ == "__main__":
    unittest.main()
