"""Unit tests for Full Ledger History deletion and Timesheets & WPS timeline deletion."""

from __future__ import annotations

import json
from pathlib import Path
import unittest

DOCS_ROOT = Path(__file__).resolve().parent.parent
WEB_ROOT = DOCS_ROOT.parent / "bookkeeping-tool"


def run_node_script(script: str) -> dict:
    from tests.js_runner import run_node_script as _run_js

    completed = _run_js(script, WEB_ROOT)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr or completed.stdout)
    return json.loads(completed.stdout.strip().splitlines()[-1])


class TestLedgerAndTimesheetDeletion(unittest.TestCase):
    def test_delete_ledger_entry_does_not_resurrect_payroll_journals_or_leave_orphan_expense_lines(self) -> None:
        script = f"""
        const fs = require('fs');
        const vm = require('vm');
        const store = {{
            'bookkeeping_history_v2': JSON.stringify([
                {{
                    id: 'exp-main-1', expenseId: 'EXP-1001', type: 'journal', status: 'posted', date: '2026-03-10',
                    entityName: 'DEWA', description: 'Expense EXP-1001 – Utilities',
                    drAcc: '6300 Utilities', crAcc: '1100 Bank Account', subtotal: '1000.00', total: '1000.00', hasFile: true
                }},
                {{
                    id: 'exp-vat-1', expenseId: 'EXP-1001', type: 'journal', status: 'posted', date: '2026-03-10',
                    entityName: 'DEWA', description: 'Input VAT – Expense EXP-1001',
                    drAcc: '1300 Input VAT Receivable', crAcc: '1100 Bank Account', subtotal: '50.00', total: '50.00'
                }},
                {{
                    id: 1710000099, type: 'customer', status: 'posted', date: '2026-03-12',
                    entityName: 'Acme Corp', invoiceNum: 'INV-1099', description: 'Advisory Retainer',
                    account: '4000 Sales Revenue', subtotal: '2000.00', tax: '100.00', total: '2100.00',
                    items: [], hasFile: true
                }},
                {{
                    type: 'journal', status: 'posted', date: '2026-03-10',
                    entityName: 'Legacy Entry A', description: 'Un-IDd Legacy A',
                    drAcc: '6000 Office Supplies', crAcc: '1000 Cash', subtotal: '120.00', total: '120.00'
                }},
                {{
                    type: 'journal', status: 'posted', date: '2026-03-10',
                    entityName: 'Legacy Entry B', description: 'Un-IDd Legacy B',
                    drAcc: '6000 Office Supplies', crAcc: '1000 Cash', subtotal: '240.00', total: '240.00'
                }}
            ]),
            'bookkeeping_stock_ledger': JSON.stringify([
                {{ id: 'stk-1', date: '2026-03-01', productName: 'Laptop', type: 'IN', qtyChange: 5, unitCost: 2000, totalValue: 10000 }}
            ]),
            'bookkeeping_inventory': JSON.stringify([
                {{ name: 'Laptop', qty: 5, cost: 2000, price: 3000 }}
            ]),
            'payroll_2026-03': JSON.stringify({{
                paymentAccount: '1100 Bank Account',
                accrueEOSB: true,
                employees: {{
                    EMP001: {{
                        name: 'Amina Al Mansoori', basic: '12,000.00', allowance: '3,000.00',
                        totalFixed: '15,000.00', daysWorked: 30, bonus: 0, loanDed: 0, deductions: 0, netPay: 15000
                    }}
                }}
            }})
        }};
        const localStorageMock = {{
            getItem: (k) => (k in store ? store[k] : null),
            setItem: (k, v) => {{ store[k] = String(v); }},
            removeItem: (k) => {{ delete store[k]; }},
            key: (i) => Object.keys(store)[i] || null,
            get length() {{ return Object.keys(store).length; }}
        }};
        const elements = {{}};
        const listeners = {{}};
        const makeEl = (id) => ({{
            id, value: '', innerHTML: '', textContent: '', innerText: '', checked: false,
            style: {{ display: 'none' }}, dataset: {{}}, children: [], options: [],
            classList: {{ add() {{}}, remove() {{}}, contains() {{ return false; }} }},
            appendChild(child) {{ this.children.push(child); }},
            hasAttribute() {{ return false; }}, setAttribute() {{}},
            addEventListener(ev, fn) {{ listeners[`${{id}}:${{ev}}`] = fn; }},
            click() {{ if (listeners[`${{id}}:click`]) listeners[`${{id}}:click`]({{ preventDefault() {{}} }}); }},
            querySelector() {{ return null; }}, querySelectorAll() {{ return []; }}
        }});
        [
            'historyBody', 'historyTable', 'emptyHistory', 'ledgerDateFrom', 'ledgerDateTo',
            'view-expense', 'expListBody', 'expListTotal', 'expCount', 'expNumber', 'expDate',
            'expPayee', 'expAmount', 'expVat', 'expTotal', 'expAccount', 'expPaidFrom', 'expDesc',
            'expRef', 'expApplyVat', 'expSaveBtn', 'expResetBtn', 'editEntryId', 'editEntryDate',
            'editEntryDesc', 'editEntryEntityName', 'editEntryRef', 'editEntrySubtotal',
            'editEntryDiscount', 'editEntryTax', 'editEntryTotal', 'editEntryAccount',
            'editEntityNameContainer', 'editEntryDescGroup', 'editEntryAccountGroup',
            'editEntryItemsContainer', 'editEntryItemsList', 'editLedgerModal', 'btnSaveEditedEntry',
            'invoiceModal', 'modalBody', 'modalFooter', 'statementEntitySelect', 'statementBody',
            'statementTotalInvoice', 'statementTotalPayment', 'statementBalance', 'cashflowForecastContainer'
        ].forEach(id => {{ elements[id] = makeEl(id); }});
        elements.statementEntitySelect.value = 'Acme Corp';
        const documentMock = {{
            readyState: 'complete',
            getElementById: (id) => elements[id] || (elements[id] = makeEl(id)),
            querySelector: () => null,
            querySelectorAll: () => [],
            createElement: (tag) => makeEl(tag),
            addEventListener: () => {{}}
        }};
        const removedAttachments = [];
        const loadedAttachments = [];
        const auditEvents = [];
        let cffRefreshed = 0;
        const windowMock = {{
            localStorage: localStorageMock, document: documentMock,
            LumenUI: {{ toast() {{}}, confirm: async () => true, validateFields: () => true }},
            LumenAttachments: {{
                offload: (list) => list,
                remove: (id) => {{ removedAttachments.push(String(id)); }},
                load: async (id) => {{ loadedAttachments.push(String(id)); return 'data:image/png;base64,AAA='; }}
            }},
            renderCashflowForecast: () => {{ cffRefreshed += 1; }},
            formatDateDdMmYy: (v) => String(v || ''),
            escHtml: (s) => String(s ?? ''),
            formatCurrency: (n) => Number(n || 0).toFixed(2)
        }};
        const context = vm.createContext({{
            window: windowMock, document: documentMock, localStorage: localStorageMock, console,
            historyTable: elements.historyTable, historyBody: elements.historyBody, emptyHistory: elements.emptyHistory,
            currentStatementMode: '',
            isLocked: () => false,
            getAssets: () => [], getAccruals: () => [], getCustomers: () => [{{ name: 'Acme Corp' }}], getSuppliers: () => [],
            getStockLedger: () => JSON.parse(store['bookkeeping_stock_ledger'] || '[]'),
            getInventory: () => JSON.parse(store['bookkeeping_inventory'] || '[]'),
            loadStockLedger: () => {{}}, loadInventory: () => {{}},
            loadCustomerDirectory: () => {{}}, loadSupplierDirectory: () => {{}},
            logAuditEvent: (action, mod, details) => {{ auditEvents.push({{ action, mod, details }}); }},
            updateKPIs: () => {{}}, renderTrialBalance: () => {{}},
            safeNum: (v) => Number(v || 0).toFixed(2),
            escHtml: windowMock.escHtml, formatCurrency: windowMock.formatCurrency,
            setTimeout, clearTimeout,
            Date, Math, Number, String, Object, Array, JSON, RegExp, Map, Set, parseFloat, parseInt, isNaN, isFinite
        }});
        vm.runInContext(fs.readFileSync({json.dumps(str(WEB_ROOT / "ar-posting-fix.js"))}, 'utf8'), context);
        context.getRawHistory = () => {{
            const list = JSON.parse(store['bookkeeping_history_v2'] || '[]');
            const repaired = list.map(windowMock.LumenPostingRepair.repairEntry);
            return windowMock.LumenPostingRepair.backfillSavedPayrolls(repaired);
        }};
        context.getHistory = () => context.getRawHistory();
        vm.runInContext(fs.readFileSync({json.dumps(str(WEB_ROOT / "expenses.js"))}, 'utf8'), context);
        vm.runInContext(fs.readFileSync({json.dumps(str(WEB_ROOT / "app-contacts-and-inventory.js"))}, 'utf8'), context);
        vm.runInContext(fs.readFileSync({json.dumps(str(WEB_ROOT / "app-journals-and-coa.js"))}, 'utf8'), context);
        vm.runInContext(fs.readFileSync({json.dumps(str(WEB_ROOT / "app-ledger-and-soa.js"))}, 'utf8'), context);
        context.updateKPIs = () => {{}};
        vm.runInContext(fs.readFileSync({json.dumps(str(WEB_ROOT / "app-ledger-actions.js"))}, 'utf8'), context);

        return (async () => {{
            const before = context.getHistory();
            const grossEntry = before.find(e => e.entityName === 'Payroll Gross 2026-03');
            const eosbEntry = before.find(e => e.entityName === 'EOSB Accrual 2026-03');
            const legacyA = before.find(e => e.entityName === 'Legacy Entry A');
            const legacyB = before.find(e => e.entityName === 'Legacy Entry B');
            const legacyBIdBefore = legacyB.id;

            await windowMock.viewFile('1710000099');
            windowMock.handleLedgerAction('1710000099', 'edit');
            elements.editEntryDesc.value = 'Updated Advisory Retainer';
            elements.btnSaveEditedEntry.click();

            windowMock.editExpenseById('EXP-1001');
            windowMock.handleLedgerAction(grossEntry.id, 'delete');
            await new Promise(r => setTimeout(r, 20));
            await windowMock.deleteEntry(eosbEntry.id);
            await windowMock.deleteEntry('exp-main-1');
            await windowMock.deleteEntry(legacyA.id);

            const after = context.getHistory();
            const legacyBAfter = after.find(e => e.entityName === 'Legacy Entry B');
            const editedInv = after.find(e => String(e.id) === '1710000099');
            const stockAfter = JSON.parse(store['bookkeeping_stock_ledger'] || '[]');
            console.log(JSON.stringify({{
                afterEntities: after.map(e => e.entityName),
                afterIds: after.map(e => String(e.id)),
                stockCount: stockAfter.length,
                expCountText: elements.expCount.textContent,
                expNumberVal: elements.expNumber.value,
                removedAttachments,
                loadedAttachments,
                editedInvDesc: editedInv ? editedInv.description : '',
                legacyIdsDistinct: legacyA.id !== legacyBIdBefore,
                legacyBIdStable: Boolean(legacyBAfter && legacyBAfter.id === legacyBIdBefore),
                auditDeleteCount: auditEvents.filter(a => a.action === 'Delete').length,
                cffRefreshed,
                soaBodyHtml: elements.statementBody.innerHTML
            }}));
        }})();
        """
        result = run_node_script(script)
        self.assertNotIn("Payroll Gross 2026-03", result["afterEntities"])
        self.assertNotIn("EOSB Accrual 2026-03", result["afterEntities"])
        self.assertEqual(result["afterEntities"].count("Payroll Net 2026-03"), 1)
        self.assertNotIn("exp-main-1", result["afterIds"])
        self.assertNotIn("exp-vat-1", result["afterIds"])
        self.assertEqual(result["stockCount"], 1)
        self.assertEqual(result["expCountText"], "0 expenses")
        self.assertEqual(result["expNumberVal"], "EXP-0001")
        self.assertIn("exp-main-1", result["removedAttachments"])
        self.assertIn("1710000099", result["loadedAttachments"])
        self.assertEqual(result["editedInvDesc"], "Updated Advisory Retainer")
        self.assertTrue(result["legacyIdsDistinct"])
        self.assertTrue(result["legacyBIdStable"])
        self.assertGreaterEqual(result["auditDeleteCount"], 4)
        self.assertGreaterEqual(result["cffRefreshed"], 4)
        self.assertIn("INV-1099", result["soaBodyHtml"])

    def test_delete_timesheet_in_edit_details_removes_saved_payroll_and_linked_ledger_entries_and_respects_lock(self) -> None:
        modals_js = (WEB_ROOT / "views-modals.js").read_text(encoding="utf-8")
        self.assertIn('id="btnDeleteTimesheet"', modals_js)
        self.assertIn("window.deleteTimesheet()", modals_js)

        script = f"""
        const fs = require('fs');
        const vm = require('vm');
        const store = {{
            'bookkeeping_employees': JSON.stringify([{{
                empId: 'EMP001', name: 'Tariq Al Hashimi', position: 'Lead Engineer',
                dateHired: '2022-09-01', basicSalary: 15000, housing: 4000, telephone: 500, allowance: 1500, totalPay: 21000
            }}])
        }};
        const localStorageMock = {{
            getItem: (k) => (k in store ? store[k] : null),
            setItem: (k, v) => {{ store[k] = String(v); }},
            removeItem: (k) => {{ delete store[k]; }},
            key: (i) => Object.keys(store)[i] || null,
            get length() {{ return Object.keys(store).length; }}
        }};
        const elements = {{}};
        const makeEl = (id) => ({{
            id, value: '', innerHTML: '', textContent: '', checked: false, disabled: false,
            style: {{ display: 'none' }}, dataset: {{}}, files: [], children: [], options: [],
            appendChild(child) {{ this.children.push(child); }},
            addEventListener() {{}}, querySelector() {{ return null; }}
        }});
        [
            'timesheetPeriod', 'payrollPaymentAccount', 'payrollAccrueEOSB', 'timesheetModal',
            'timesheetBody', 'btnDeleteTimesheet', 'savedTimesheetsContainer', 'eosbSummaryContainer',
            'filterTimesheetMonth', 'filterTimesheetEmployee', 'wpsSifPreviewBox',
            'incomeStatementContainer', 'balanceSheetContainer', 'cashflowContainer',
            'equityStatementContainer', 'cashflowForecastContainer', 'tbBody', 'tbTotalDebit',
            'tbTotalCredit', 'closeMonthDate', 'btnCloseMonth'
        ].forEach(id => {{ elements[id] = makeEl(id); }});
        elements.timesheetPeriod.value = '2026-03';
        elements.payrollPaymentAccount.value = '1100 Bank Account';
        elements.payrollAccrueEOSB.checked = true;

        const rowMock = {{
            dataset: {{ empId: 'EMP001' }},
            children: [
                {{ textContent: 'EMP001' }}, {{ textContent: 'Tariq Al Hashimi' }},
                {{ textContent: '15,000.00' }}, {{ textContent: '6,000.00' }}, {{ textContent: '21,000.00' }}
            ],
            querySelector: (sel) => ({{
                '.ts-days': {{ value: '30' }}, '.ts-bonus': {{ value: '1000' }},
                '.ts-loan': {{ value: '500' }}, '.ts-other': {{ value: '100' }},
                '.ts-net': {{ textContent: '21,400.00' }}
            }}[sel] || null)
        }};
        const documentMock = {{
            getElementById: (id) => elements[id] || null,
            querySelector: () => null,
            querySelectorAll: (sel) => (sel === '.timesheet-row' ? [rowMock] : []),
            createElement: (tag) => makeEl(tag),
            addEventListener: () => {{}}
        }};
        const toasts = [];
        const auditEvents = [];
        let cffRefreshed = 0;
        const windowMock = {{
            localStorage: localStorageMock, document: documentMock,
            LumenUI: {{
                toast: (msg, type) => {{ toasts.push({{ msg, type }}); }},
                confirm: async () => true,
                validateFields: () => true
            }},
            LumenAttachments: {{ offload: (list) => list }},
            renderCashflowForecast: () => {{ cffRefreshed += 1; }},
            parseAmount: (val) => parseFloat(String(val ?? '').replace(/,/g, '')) || 0,
            isExpenseAccount: (acc) => String(acc || '').startsWith('6') || String(acc || '').startsWith('5'),
            getManualSettlement: () => 0,
            formatDateDdMmYy: (v) => String(v || ''),
            escHtml: (s) => String(s ?? ''),
            formatCurrency: (n) => Number(n || 0).toLocaleString('en-US', {{ minimumFractionDigits: 2, maximumFractionDigits: 2 }})
        }};
        const context = vm.createContext({{
            window: windowMock, document: documentMock, localStorage: localStorageMock, console,
            timesheetPeriod: elements.timesheetPeriod, timesheetBody: elements.timesheetBody,
            CHART_OF_ACCOUNTS: [],
            tbDateFrom: null, tbDateTo: null, taxDateFrom: null, taxDateTo: null, btnFilterTb: null,
            getEmployees: () => JSON.parse(store['bookkeeping_employees'] || '[]'),
            getRawHistory: () => JSON.parse(store['bookkeeping_history_v2'] || '[]'),
            getHistory: () => JSON.parse(store['bookkeeping_history_v2'] || '[]'),
            logAuditEvent: (action, mod, details) => {{ auditEvents.push({{ action, mod, details }}); }},
            loadEmployeeDirectory: () => {{}},
            loadHistory: () => {{}}, loadInventory: () => {{}}, loadStockLedger: () => {{}},
            loadCustomerDirectory: () => {{}}, loadSupplierDirectory: () => {{}},
            updateKPIs: () => {{}}, renderTrialBalance: () => {{}},
            renderIncomeStatement: () => {{}}, renderBalanceSheet: () => {{}},
            renderCashflow: () => {{}}, renderEquityStatement: () => {{}},
            escHtml: windowMock.escHtml, formatCurrency: windowMock.formatCurrency,
            Date, Math, Number, String, Object, Array, JSON, Map, Set, parseFloat, parseInt, isNaN, isFinite
        }});
        store['bookkeeping_closed_date'] = '2026-03-31';
        vm.runInContext(fs.readFileSync({json.dumps(str(WEB_ROOT / "app-contacts-and-inventory.js"))}, 'utf8'), context);
        vm.runInContext(fs.readFileSync({json.dumps(str(WEB_ROOT / "app-payroll-and-wps.js"))}, 'utf8'), context);
        context.loadSavedTimesheets = windowMock.loadSavedTimesheets;
        context.loadTimesheet = windowMock.loadTimesheet;
        vm.runInContext(fs.readFileSync({json.dumps(str(WEB_ROOT / "app-settings-and-kpis.js"))}, 'utf8'), context);

        return (async () => {{
            delete store['bookkeeping_closed_date'];
            elements.timesheetPeriod.value = '2026-03';
            windowMock.savePayroll();
            windowMock.openTimesheetModal('2026-03');
            const deleteBtnVisibleBefore = elements.btnDeleteTimesheet.style.display !== 'none' && !elements.btnDeleteTimesheet.disabled;
            const savedCountBefore = JSON.parse(store['bookkeeping_history_v2'] || '[]').length;

            store['bookkeeping_closed_date'] = '2026-03-31';
            await windowMock.deleteTimesheet('2026-03');
            const existsWhileLocked = Boolean(store['payroll_2026-03']);

            delete store['bookkeeping_closed_date'];
            await windowMock.deleteTimesheet('2026-03');
            const existsAfterDelete = Boolean(store['payroll_2026-03']);
            const historyAfterDelete = JSON.parse(store['bookkeeping_history_v2'] || '[]');
            const modalDisplayAfter = elements.timesheetModal.style.display;
            const deleteBtnVisibleAfter = elements.btnDeleteTimesheet.style.display !== 'none';

            console.log(JSON.stringify({{
                deleteBtnVisibleBefore,
                savedCountBefore,
                existsWhileLocked,
                existsAfterDelete,
                historyCountAfterDelete: historyAfterDelete.length,
                modalDisplayAfter,
                deleteBtnVisibleAfter,
                savedTimesheetsHtml: elements.savedTimesheetsContainer.innerHTML,
                auditActions: auditEvents.map(a => a.action),
                cffRefreshed
            }}));
        }})();
        """
        result = run_node_script(script)
        self.assertTrue(result["deleteBtnVisibleBefore"])
        self.assertEqual(result["savedCountBefore"], 5)
        self.assertTrue(result["existsWhileLocked"])
        self.assertFalse(result["existsAfterDelete"])
        self.assertEqual(result["historyCountAfterDelete"], 0)
        self.assertEqual(result["modalDisplayAfter"], "none")
        self.assertFalse(result["deleteBtnVisibleAfter"])
        self.assertNotIn("Pay Period: 2026-03", result["savedTimesheetsHtml"])
        self.assertIn("Delete", result["auditActions"])
        self.assertEqual(result["auditActions"][-1], "Delete")
        self.assertEqual(result["cffRefreshed"], 2)

    def test_real_dom_timesheet_modal_delete_button_and_dialog_z_index(self) -> None:
        from tests.dom_harness import DomComponentHarness

        dom = DomComponentHarness()
        dom.mount(
            '<div id="savedTimesheetsContainer"></div>',
            modules=("i18n.js", "ui-feedback.js", "views-modals.js"),
        )
        result = dom.run("""
            const modalEl = document.getElementById('timesheetModal');
            const deleteBtn = document.getElementById('btnDeleteTimesheet');
            modalEl.style.display = 'flex';
            const modalZ = parseInt(getComputedStyle(modalEl).zIndex, 10) || 10000;
            const deleteBtnVisible = getComputedStyle(deleteBtn).display !== 'none' && !deleteBtn.disabled;
            const deleteBtnText = deleteBtn.textContent.trim();

            if (window.LumenI18n && typeof window.LumenI18n.setLang === 'function') {
                window.LumenI18n.setLang('ar');
            }
            const pending = window.LumenUI.confirm({
                title: 'Delete timesheet?',
                message: 'Timesheet and all posted payroll & EOSB journal entries for "2026-03" will be permanently deleted.',
                confirmText: 'Delete timesheet',
                danger: true,
            });
            await tick(50);
            const backdrop = document.querySelector('.lumen-dialog-backdrop');
            const dialogZ = parseInt(getComputedStyle(backdrop).zIndex, 10);
            const arDialogTitle = backdrop.querySelector('.lumen-dialog__title').textContent.trim();
            const arDialogMsg = backdrop.querySelector('.lumen-dialog__message').textContent.trim();
            const arConfirmBtn = backdrop.querySelector('[data-dialog-action="confirm"]').textContent.trim();
            const toastEl = window.LumenUI.toast('Timesheet for 2026-03 deleted.', 'info');
            await tick(30);
            const arToastMsg = toastEl.querySelector('.lumen-toast__message').textContent.trim();
            const toastRegion = toastEl.closest('.lumen-toast-region');
            const toastZ = parseInt(getComputedStyle(toastRegion).zIndex, 10);
            backdrop.querySelector('[data-dialog-action="confirm"]').click();
            const confirmed = await pending;

            done({
                deleteBtnVisible,
                deleteBtnText,
                arDeleteBtnText: deleteBtn.textContent.trim(),
                arDialogTitle,
                arDialogMsg,
                arConfirmBtn,
                arToastMsg,
                dialogAboveModal: dialogZ > modalZ,
                toastAboveDialog: toastZ > dialogZ,
                confirmed,
            });
        """)
        self.assertTrue(result["deleteBtnVisible"])
        self.assertEqual(result["deleteBtnText"], "Delete Timesheet")
        self.assertEqual(result["arDeleteBtnText"], "حذف سجل الدوام")
        self.assertEqual(result["arDialogTitle"], "حذف سجل الدوام؟")
        self.assertIn("2026-03", result["arDialogMsg"])
        self.assertIn("حذف", result["arDialogMsg"])
        self.assertEqual(result["arConfirmBtn"], "حذف سجل الدوام")
        self.assertEqual(result["arToastMsg"], "تم حذف سجل الدوام للفترة 2026-03.")
        self.assertTrue(result["dialogAboveModal"])
        self.assertTrue(result["toastAboveDialog"])
        self.assertTrue(result["confirmed"])


if __name__ == "__main__":
    unittest.main()
