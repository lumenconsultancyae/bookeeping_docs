"""Unit tests for professional Payslip document rendering and Timesheet & WPS employee filter."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
import unittest


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
WEB_ROOT = WORKSPACE_ROOT / "bookkeeping-tool"
DOCS_ROOT = WORKSPACE_ROOT / "bookeeping_docs"


def run_node_script(script: str) -> dict:
    from tests.js_runner import run_node_script as _run_js
    completed = _run_js(script, WEB_ROOT)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr or completed.stdout)
    return json.loads(completed.stdout.strip().splitlines()[-1])


class TestPayslipAndTimesheetEmployeeFilter(unittest.TestCase):
    """Verify professional payslip document details and timesheet employee dropdown completeness."""

    def test_settings_view_contains_company_phone_input(self) -> None:
        views_source = (WEB_ROOT / "views-reports-and-settings.js").read_text(encoding="utf-8")
        self.assertIn('id="companyPhone"', views_source)

    def test_timesheet_employee_filter_lists_all_employees_even_without_saved_timesheets(self) -> None:
        script = f"""
        const fs = require('fs'), vm = require('vm'), store = {{}}, elements = {{}};
        const localStorageMock = {{
            getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => {{ store[k] = String(v); }},
            removeItem: (k) => {{ delete store[k]; }}, key: (i) => Object.keys(store)[i] || null,
            get length() {{ return Object.keys(store).length; }}
        }};
        const makeEl = (id) => ({{
            id, value: '', innerHTML: '', textContent: '', style: {{}}, dataset: {{}}, children: [], options: [],
            appendChild(child) {{ this.children.push(child); if (child && child.tagName === 'OPTION') this.options.push(child); }},
            addEventListener() {{}}, querySelector() {{ return null; }}, reset() {{}}
        }});
        ['filterTimesheetEmployee', 'filterTimesheetMonth', 'savedTimesheetsContainer', 'employeeDirectoryBody'].forEach(id => {{ elements[id] = makeEl(id); }});
        Object.defineProperty(elements.filterTimesheetEmployee, 'innerHTML', {{
            get() {{ return this._html || ''; }},
            set(v) {{ this._html = v; if (v === '') {{ this.children = []; this.options = []; }} }}
        }});
        const documentMock = {{
            getElementById: (id) => elements[id] || null, querySelector: () => null, querySelectorAll: () => [],
            createElement: (tag) => ({{ tagName: tag.toUpperCase(), value: '', textContent: '', style: {{}} }})
        }};
        const windowMock = {{
            localStorage: localStorageMock, document: documentMock,
            LumenUI: {{ toast() {{}}, confirm: async () => true, validateFields: () => true }}, alert: () => {{}}, confirm: () => true
        }};
        const context = vm.createContext({{
            window: windowMock, document: documentMock, localStorage: localStorageMock, console,
            getHistory: () => [], getRawHistory: () => [], logAuditEvent: () => {{}},
            escHtml: (s) => String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'),
            formatCurrency: (n) => Number(n || 0).toLocaleString('en-US', {{ minimumFractionDigits: 2, maximumFractionDigits: 2 }}),
            Date, Math, Number, String, Object, Array, JSON, Map, Set, parseFloat, parseInt, isNaN
        }});
        windowMock.formatCurrency = context.formatCurrency; windowMock.escHtml = context.escHtml;
        store['bookkeeping_employees'] = JSON.stringify([
            {{ name: 'Amina Al Mansoori', position: 'Senior Accountant', dateHired: '2023-01-15', empId: 'EMP001', basicSalary: 12000, totalPay: 15000 }},
            {{ name: 'Rashed Al Nuaimi', position: 'Operations Manager', dateHired: '2022-06-01', empId: '', basicSalary: 14000, totalPay: 18000 }},
            {{ name: 'Fatima Al Zaabi', position: 'HR Specialist', dateHired: '2024-03-10', basicSalary: 9000, totalPay: 11000 }}
        ]);
        vm.runInContext(fs.readFileSync({json.dumps(str(WEB_ROOT / "app-contacts-and-inventory.js"))}, 'utf8'), context);
        vm.runInContext(fs.readFileSync({json.dumps(str(WEB_ROOT / "app-payroll-and-wps.js"))}, 'utf8'), context);
        windowMock.loadSavedTimesheets();
        const optionLabels = elements.filterTimesheetEmployee.options.map(o => ({{ value: o.value, text: o.textContent }}));
        vm.runInContext(`saveEmployee({{ name: 'Omar Al Suwaidi', position: 'Financial Analyst', dateHired: '2025-02-01', empId: 'EMP004', basicSalary: 10000, totalPay: 12500 }});`, context);
        const updatedOptionLabels = elements.filterTimesheetEmployee.options.map(o => ({{ value: o.value, text: o.textContent }}));
        store['payroll_2026-01'] = JSON.stringify({{ 'T-0': {{ name: 'Amina Al Mansoori', basic: '12,000.00', allowance: '3,000.00', totalFixed: '15,000.00', daysWorked: 30, netPay: '15,000.00' }} }});
        store['payroll_2026-02'] = JSON.stringify({{
            paymentAccount: '1100 Bank Account',
            employees: {{
                EMP001: {{ name: 'Amina Al Mansoori', basic: '12,000.00', allowance: '3,000.00', totalFixed: '15,000.00', daysWorked: 30, netPay: '15,000.00' }},
                EMP002: {{ name: 'Rashed Al Nuaimi', basic: '14,000.00', allowance: '4,000.00', totalFixed: '18,000.00', daysWorked: 30, netPay: '18,000.00' }}
            }}
        }});
        windowMock.loadSavedTimesheets();
        const afterLegacyOptions = elements.filterTimesheetEmployee.options.map(o => ({{ value: o.value, text: o.textContent }}));
        elements.filterTimesheetEmployee.value = 'EMP002'; windowMock.loadSavedTimesheets();
        const filteredEmp2Html = elements.savedTimesheetsContainer.innerHTML;
        elements.filterTimesheetEmployee.value = 'EMP004'; windowMock.loadSavedTimesheets();
        const filteredEmp4Html = elements.savedTimesheetsContainer.innerHTML;
        console.log(JSON.stringify({{ optionLabels, updatedOptionLabels, afterLegacyOptions, filteredEmp2Html, filteredEmp4Html }}));
        """
        result = run_node_script(script)
        initial_texts = [opt["text"] for opt in result["optionLabels"]]
        self.assertEqual(initial_texts[0], "All Employees")
        self.assertEqual(len(initial_texts), 4)
        for name in ("Amina Al Mansoori", "Rashed Al Nuaimi", "Fatima Al Zaabi"):
            self.assertTrue(any(name in t for t in initial_texts))
        updated_texts = [opt["text"] for opt in result["updatedOptionLabels"]]
        self.assertEqual(len(updated_texts), 5)
        self.assertTrue(any("Omar Al Suwaidi" in t for t in updated_texts))
        legacy_values = [opt["value"] for opt in result["afterLegacyOptions"]]
        self.assertNotIn("T-0", legacy_values)
        self.assertEqual(len(legacy_values), 5)
        self.assertIn("Rashed Al Nuaimi", result["filteredEmp2Html"])
        self.assertIn("18,000.00", result["filteredEmp2Html"])
        self.assertNotIn("Amina Al Mansoori", result["filteredEmp2Html"])
        self.assertNotIn("No timesheet records found", result["filteredEmp2Html"])
        self.assertEqual(result["filteredEmp4Html"].count("No timesheet records found"), 1)

    def test_generate_payslip_renders_professional_document_with_employee_and_company_details(self) -> None:
        script = f"""
        const fs = require('fs'), vm = require('vm'), store = {{}}, elements = {{}};
        const localStorageMock = {{
            getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => {{ store[k] = String(v); }},
            removeItem: (k) => {{ delete store[k]; }}, key: (i) => Object.keys(store)[i] || null,
            get length() {{ return Object.keys(store).length; }}
        }};
        const makeEl = (id) => ({{
            id, value: '', innerHTML: '', textContent: '', style: {{ display: 'none' }},
            dataset: {{}}, files: [], children: [], options: [],
            appendChild(child) {{ this.children.push(child); }}, addEventListener() {{}}, querySelector() {{ return null; }}
        }});
        ['invoiceModal', 'invoiceDocument', 'modalFooter', 'companyName', 'companyAddress', 'companyPhone', 'companyTrn', 'companyLogoInput', 'companyLogoPreview', 'btnSaveCompanySettings', 'currencyRatesBody', 'resCurrency'].forEach(id => {{ elements[id] = makeEl(id); }});
        elements.modalFooter.innerHTML = '<button id="staleInvoiceBtn">Issue Credit Note (CRN)</button>';
        let printHtml = '';
        const printWindowMock = {{ document: {{ write: (html) => {{ printHtml += html; }}, close: () => {{}} }}, focus: () => {{}}, print: () => {{}} }};
        const documentMock = {{ getElementById: (id) => elements[id] || null, querySelector: () => null, querySelectorAll: () => [], createElement: (tag) => makeEl(tag) }};
        const windowMock = {{
            localStorage: localStorageMock, document: documentMock,
            LumenUI: {{ toast() {{}}, confirm: async () => true, validateFields: () => true }},
            open: () => printWindowMock, alert: () => {{}}, confirm: () => true
        }};
        const context = vm.createContext({{
            window: windowMock, document: documentMock, localStorage: localStorageMock, console,
            setTimeout: (fn) => fn(), getHistory: () => [], getRawHistory: () => [],
            logAuditEvent: () => {{}}, loadEmployeeDirectory: () => {{}}, escHtml: (s) => String(s ?? ''),
            formatCurrency: (n) => Number(n || 0).toLocaleString('en-US', {{ minimumFractionDigits: 2, maximumFractionDigits: 2 }}),
            numberToWords: (n) => `AED ${{n}} Only`, CHART_OF_ACCOUNTS: [],
            Date, Math, Number, String, Object, Array, JSON, Map, Set, parseFloat, parseInt, isNaN
        }});
        windowMock.formatCurrency = context.formatCurrency; windowMock.numberToWords = context.numberToWords; windowMock.escHtml = context.escHtml;
        store['bookkeeping_settings'] = JSON.stringify({{
            companyName: 'Lumen & Associates <Advisory> Consultancy LLC',
            companyAddress: 'Business Bay, Dubai, UAE', companyPhone: '+971 56 471 8587', companyTrn: '100492817300003',
            companyLogo: 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==',
            wpsEmployerId: '0001234567890'
        }});
        store['bookkeeping_employees'] = JSON.stringify([{{
            empId: 'EMP001', name: 'Tariq Al Hashimi', position: 'Lead Mechanical Engineer',
            dateHired: '2022-09-01', labourCard: '12345678901234', iban: 'AE070331234567890123456',
            routingCode: '302620122', basicSalary: 15000, housing: 4000, telephone: 500, allowance: 1500, totalPay: 21000
        }}]);
        store['payroll_2026-03'] = JSON.stringify({{
            paymentAccount: '1005 Bank Account',
            employees: {{ EMP001: {{ name: 'Tariq Al Hashimi', basic: '15,000.00', allowance: '6,000.00', totalFixed: '21,000.00', daysWorked: 28, unpaidLeave: 2, bonus: 1000, loanDed: 500, deductions: 100, netPay: '20,000.00' }} }}
        }});
        vm.runInContext(fs.readFileSync({json.dumps(str(WEB_ROOT / "app-contacts-and-inventory.js"))}, 'utf8'), context);
        windowMock.getEmployees = context.getEmployees;
        vm.runInContext(fs.readFileSync({json.dumps(str(WEB_ROOT / "app-settings-and-kpis.js"))}, 'utf8'), context);
        windowMock.generatePayslip('2026-03', 'EMP001');
        console.log(JSON.stringify({{ modalDisplay: elements.invoiceModal.style.display, modalHtml: elements.invoiceDocument.innerHTML, footerHtml: elements.modalFooter.innerHTML, printHtml }}));
        """
        result = run_node_script(script)
        self.assertEqual(result["modalDisplay"], "flex")
        self.assertIn("Print / PDF Payslip", result["footerHtml"])
        self.assertNotIn("Issue Credit Note", result["footerHtml"])
        for doc_html in (result["modalHtml"], result["printHtml"]):
            for expected in (
                "Tariq Al Hashimi", "EMP001", "Lead Mechanical Engineer", "01/09/22",
                "Lumen &amp; Associates &lt;Advisory&gt; Consultancy LLC",
                "Business Bay, Dubai, UAE", "+971 56 471 8587", "data:image/png;base64,",
                "15,000.00", "4,000.00", "20,000.00",
            ):
                self.assertIn(expected, doc_html)
            self.assertNotIn("<Advisory>", doc_html)
            self.assertNotIn("1005 Bank Account", doc_html)

    def test_save_payroll_posts_journals_and_records_salaries_in_pnl(self) -> None:
        script = f"""
        const fs = require('fs'), vm = require('vm'), store = {{}}, elements = {{}};
        const localStorageMock = {{
            getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => {{ store[k] = String(v); }},
            removeItem: (k) => {{ delete store[k]; }}, key: (i) => Object.keys(store)[i] || null,
            get length() {{ return Object.keys(store).length; }}
        }};
        const makeEl = (id) => ({{
            id, value: '', innerHTML: '', textContent: '', checked: false,
            style: {{ display: 'none' }}, dataset: {{}}, files: [], children: [], options: [],
            appendChild(child) {{ this.children.push(child); }}, addEventListener() {{}}, querySelector() {{ return null; }}
        }});
        [
            'timesheetPeriod', 'payrollPaymentAccount', 'payrollAccrueEOSB', 'timesheetModal',
            'incomeStatementContainer', 'balanceSheetContainer', 'cashflowContainer',
            'equityStatementContainer', 'tbBody', 'tbTotalDebit', 'tbTotalCredit',
            'vatOutputSummary', 'vatInputSummary', 'vatNetSummary',
            'vatBox1', 'vatBox2', 'vatBox3', 'vatBox4', 'vatBox5', 'vatBox6', 'vatBox7', 'vatBox8',
            'vatBox9', 'vatBox10', 'vatBox11', 'vatBox12', 'vatBox13', 'vatBox14',
            'ctTotalRevenue', 'ctTotalExpenses', 'ctNetProfit', 'ctAddBacks', 'ctTaxableIncome', 'ctPayable',
            'kpiBankBalanceHero', 'kpiExpenses', 'companyName', 'companyAddress',
            'companyPhone', 'companyTrn', 'companyLogoInput', 'companyLogoPreview',
            'btnSaveCompanySettings', 'currencyRatesBody', 'resCurrency'
        ].forEach(id => {{ elements[id] = makeEl(id); }});
        elements.timesheetPeriod.value = '2026-03';
        elements.payrollPaymentAccount.value = '1100 Bank Account';
        elements.payrollAccrueEOSB.checked = true;
        const rowMock = {{
            dataset: {{ empId: 'EMP001' }},
            children: [{{ textContent: 'EMP001' }}, {{ textContent: 'Tariq Al Hashimi' }}, {{ textContent: '15,000.00' }}, {{ textContent: '6,000.00' }}, {{ textContent: '21,000.00' }}],
            querySelector: (sel) => ({{ '.ts-days': {{ value: '30' }}, '.ts-bonus': {{ value: '1000' }}, '.ts-loan': {{ value: '500' }}, '.ts-other': {{ value: '100' }}, '.ts-net': {{ textContent: '21,400.00' }} }}[sel] || null)
        }};
        const documentMock = {{ getElementById: (id) => elements[id] || null, querySelector: () => null, querySelectorAll: (sel) => (sel === '.timesheet-row' ? [rowMock] : []), createElement: (tag) => makeEl(tag) }};
        let lockedFlag = false;
        const windowMock = {{
            localStorage: localStorageMock, document: documentMock,
            LumenUI: {{ toast() {{}}, confirm: async () => true, validateFields: () => true }},
            LumenAttachments: {{ offload: (list) => list }},
            parseAmount: (val) => parseFloat(String(val ?? '').replace(/,/g, '')) || 0,
            isExpenseAccount: (acc) => String(acc || '').startsWith('6') || String(acc || '').startsWith('5'),
            getManualSettlement: () => 0, alert: () => {{}}, confirm: () => true
        }};
        const coa = [
            {{ code: '1005', name: 'Bank', type: 'Asset' }}, {{ code: '1210', name: 'Employee Advances/Loans', type: 'Asset' }},
            {{ code: '2100', name: 'Accrued Liabilities', type: 'Liability' }}, {{ code: '2120', name: 'Provision for EOSB', type: 'Liability' }},
            {{ code: '6500', name: 'Payroll / Salaries', type: 'Expense' }}, {{ code: '6520', name: 'EOSB & Leave Expense', type: 'Expense' }}
        ];
        const context = vm.createContext({{
            window: windowMock, document: documentMock, localStorage: localStorageMock, console,
            timesheetPeriod: elements.timesheetPeriod, CHART_OF_ACCOUNTS: coa,
            tbDateFrom: null, tbDateTo: null, taxDateFrom: null, taxDateTo: null, btnFilterTb: null,
            isLocked: () => lockedFlag,
            getRawHistory: () => JSON.parse(store['bookkeeping_history_v2'] || '[]'),
            getHistory: () => JSON.parse(store['bookkeeping_history_v2'] || '[]'),
            logAuditEvent: () => {{}}, loadEmployeeDirectory: () => {{}}, loadSavedTimesheets: () => {{}},
            loadHistory: () => {{}}, loadInventory: () => {{}}, loadStockLedger: () => {{}},
            loadCustomerDirectory: () => {{}}, loadSupplierDirectory: () => {{}},
            updateKPIs: () => {{}}, renderTrialBalance: () => {{}}, renderIncomeStatement: () => {{}}, renderBalanceSheet: () => {{}},
            escHtml: (s) => String(s ?? ''),
            formatCurrency: (n) => Number(n || 0).toLocaleString('en-US', {{ minimumFractionDigits: 2, maximumFractionDigits: 2 }}),
            Date, Math, Number, String, Object, Array, JSON, Map, Set, parseFloat, parseInt, isNaN
        }});
        windowMock.formatCurrency = context.formatCurrency; windowMock.escHtml = context.escHtml;
        store['bookkeeping_employees'] = JSON.stringify([{{ empId: 'EMP001', name: 'Tariq Al Hashimi', position: 'Lead Engineer', dateHired: '2022-09-01', basicSalary: 15000, housing: 4000, telephone: 500, allowance: 1500, totalPay: 21000 }}]);
        ['app-contacts-and-inventory.js', 'app-settings-and-kpis.js', 'app-reports-and-fpa.js', 'app-supplier-bills.js', 'app-quotes-pos-recurring.js'].forEach(f => {{
            vm.runInContext(fs.readFileSync({json.dumps(str(WEB_ROOT))}+'/'+f, 'utf8'), context);
        }});
        store['bookkeeping_closed_date'] = '2026-03-31'; windowMock.savePayroll();
        const lockedCount = JSON.parse(store['bookkeeping_history_v2'] || '[]').length;
        delete store['bookkeeping_closed_date']; windowMock.savePayroll(); windowMock.savePayroll();
        vm.runInContext('renderIncomeStatement(); renderBalanceSheet(); renderTrialBalance(); renderCashflow();', context);
        const history = JSON.parse(store['bookkeeping_history_v2'] || '[]');
        console.log(JSON.stringify({{ lockedCount, historyCount: history.length, statuses: history.map(h => h.status), pnlHtml: elements.incomeStatementContainer.innerHTML, bsHtml: elements.balanceSheetContainer.innerHTML, tbHtml: elements.tbBody.innerHTML, cfHtml: elements.cashflowContainer.innerHTML }}));
        """
        result = run_node_script(script)
        self.assertEqual(result["lockedCount"], 0)
        self.assertEqual(result["historyCount"], 5)
        self.assertTrue(all(s == "posted" for s in result["statuses"]))
        self.assertIn("6500 Payroll / Salaries", result["pnlHtml"])
        self.assertIn("21,900.00", result["pnlHtml"])
        self.assertIn("6520 EOSB & Leave Expense", result["pnlHtml"])
        self.assertNotIn("1100 1100", result["tbHtml"])
        self.assertIn("Change in Employee Advances / Loans (1210)", result["cfHtml"])
        self.assertIn("-21,400.00", result["cfHtml"])

    def test_ar_posting_fix_promotes_existing_unposted_payroll_journals_and_backfills_saved_payrolls(self) -> None:
        script = f"""
        const fs = require('fs'), vm = require('vm');
        const store = {{
            'bookkeeping_history_v2': JSON.stringify([
                {{ id: 'jv-1', type: 'journal', date: '2026-02-28', entityName: 'Payroll Gross 2026-02', description: 'Monthly Payroll Run - Gross 2026-02', drAcc: '6500 Payroll / Salaries', crAcc: '2100 Accrued Liabilities', subtotal: '15000.00', total: '15000.00' }},
                {{ id: 'jv-2', type: 'journal', date: '2026-02-28', entityName: 'Payroll Net 2026-02', description: 'Monthly Payroll Run - Net Paid 2026-02', drAcc: '2100 Accrued Liabilities', crAcc: '1005 Bank', subtotal: '15000.00', total: '15000.00' }}
            ]),
            'payroll_2026-01': JSON.stringify({{ paymentAccount: '1005 Bank', accrueEOSB: true, employees: {{ EMP001: {{ name: 'Amina Al Mansoori', basic: '12,000.00', allowance: '3,000.00', totalFixed: '15,000.00', daysWorked: 30, bonus: 0, loanDed: 0, deductions: 0, netPay: 15000 }} }} }}),
            'payroll_2025-12': JSON.stringify({{ 'T-0': {{ name: 'Legacy Employee', unpaidLeave: 3, additions: 500, loanDed: 200, deductions: 100, netPay: 13700 }} }})
        }};
        const localStorageMock = {{
            getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => {{ store[k] = String(v); }},
            removeItem: (k) => {{ delete store[k]; }}, key: (i) => Object.keys(store)[i] || null,
            get length() {{ return Object.keys(store).length; }}
        }};
        const context = vm.createContext({{ window: {{ localStorage: localStorageMock }}, localStorage: localStorageMock, console, Date, Math, Number, String, Object, Array, JSON, RegExp, parseFloat, parseInt, isNaN, isFinite }});
        vm.runInContext(fs.readFileSync({json.dumps(str(WEB_ROOT / "ar-posting-fix.js"))}, 'utf8'), context);
        console.log(JSON.stringify({{ repaired: JSON.parse(store['bookkeeping_history_v2'] || '[]') }}));
        """
        result = run_node_script(script)
        repaired = result["repaired"]
        self.assertTrue(all(e.get("status") == "posted" for e in repaired))
        entities = [e.get("entityName") for e in repaired]
        self.assertIn("Payroll Gross 2026-02", entities)
        self.assertIn("Payroll Gross 2026-01", entities)
        self.assertIn("EOSB Accrual 2026-01", entities)
        self.assertIn("Payroll Gross 2025-12", entities)

    def test_welcome_plans_basic_50_aed_one_month_free_promo_and_payment_links(self) -> None:
        script = f"""
        const fs = require('fs');
        const vm = require('vm');
        const elements = {{}};
        let domLoadedFn = null;
        const makeEl = (id) => ({{
            id, value: '', innerHTML: '', textContent: '', hidden: false, disabled: false,
            dataset: {{}}, style: {{}}, classList: {{ toggle() {{}} }},
            setAttribute() {{}}, addEventListener() {{}}, focus() {{}}, reset() {{}}
        }});
        [
            'year', 'plans', 'setupPlanSelect', 'setupPlanName', 'topbarGuestActions',
            'topbarUserActions', 'footerAdminLink', 'btnOpenRegister', 'btnWelcomeSignOut',
            'btnOpenSignIn', 'btnSetupCancel', 'setupModal', 'setupForm', 'btnSignInCancel',
            'signInModal', 'signInForm', 'btnLegalClose', 'legalModal',
            'btnPlanRequestCancel', 'btnPlanRequestConfirm', 'planRequestModal'
        ].forEach(id => {{ elements[id] = makeEl(id); }});
        const billingToggle = {{ addEventListener() {{}} }};
        const documentMock = {{
            getElementById: (id) => elements[id] || makeEl(id),
            querySelector: (sel) => (sel === '.billing-toggle' ? billingToggle : null),
            querySelectorAll: () => [],
            addEventListener: (ev, fn) => {{ if (ev === 'DOMContentLoaded') domLoadedFn = fn; }}
        }};
        const windowMock = {{
            document: documentMock, location: {{ hash: '', search: '' }},
            localStorage: {{ getItem: () => null, setItem() {{}} }},
            LumenProfiles: {{ isAuthenticated: () => false }}
        }};
        const context = vm.createContext({{
            window: windowMock, document: documentMock, localStorage: windowMock.localStorage,
            URLSearchParams, console, Date, Math, Number, String, Object, Array, JSON
        }});
        vm.runInContext(fs.readFileSync({json.dumps(str(WEB_ROOT / "welcome-plans.js"))}, 'utf8'), context);
        vm.runInContext(fs.readFileSync({json.dumps(str(WEB_ROOT / "welcome.js"))}, 'utf8'), context);
        if (domLoadedFn) domLoadedFn();
        console.log(JSON.stringify({{
            plans: windowMock.LUMEN_PLANS,
            plansHtml: elements.plans.innerHTML,
            selectHtml: elements.setupPlanSelect.innerHTML
        }}));
        """
        result = run_node_script(script)
        plans = {p["id"]: p for p in result["plans"]}
        self.assertEqual(plans["basic"]["monthly"], 50)
        self.assertEqual(plans["advance"]["monthly"], 75)
        self.assertEqual(plans["premium"]["monthly"], 100)
        for pid in ("basic", "advance", "premium"):
            self.assertIn("1 Month Free", plans[pid].get("promo", ""))
            self.assertNotIn("paymentLink", plans[pid])
            self.assertNotIn(f'id="btnPay-{pid}"', result["plansHtml"])
        self.assertEqual(result["plansHtml"].count("1 Month Free"), 3)
        self.assertIn("Basic — AED 50 / month", result["selectHtml"])

        admin_html = (WEB_ROOT / "admin.html").read_text(encoding="utf-8")
        self.assertIn("Basic (AED 50)", admin_html)
        self.assertIn("Basic — AED 50 / mo (30 inv)", admin_html)
        self.assertNotIn("AED 35", admin_html)

        i18n_js = (WEB_ROOT / "i18n.js").read_text(encoding="utf-8")
        for key in (
            "Company Contact Number",
            "6520 EOSB & Leave Expense",
            "Payslip",
            "All Employees",
            "Basic — AED 50 / month (1 Month Free)",
        ):
            self.assertIn(f"'{key}':", i18n_js)

        for doc_rel in ("docs/product/prd-product-requirements.md", "docs/product/user-guide-and-release-notes.md"):
            doc_text = (DOCS_ROOT / doc_rel).read_text(encoding="utf-8")
            self.assertIn("AED 50/mo", doc_text)
            self.assertNotIn("AED 35/mo", doc_text)
        arch_text = (DOCS_ROOT / "docs/technical/architecture-and-execution-flow.md").read_text(encoding="utf-8")
        self.assertIn("38 standard accounts", arch_text)
        self.assertIn("6520 EOSB & Leave Expense", arch_text)
        self.assertIn("companyPhone", arch_text)
        for doc_rel in ("README.md", "docs/technical/operational-runbook.md"):
            self.assertIn("test_payslip_and_timesheet_filter.py", (DOCS_ROOT / doc_rel).read_text(encoding="utf-8"))

    def test_clear_history_and_delete_payroll_entry_give_general_ledger_a_fresh_start(self) -> None:
        script = f"""
        const fs = require('fs');
        const vm = require('vm');
        const store = {{
            'bookkeeping_history_v2': JSON.stringify([
                {{ id: 'payroll_2026-11_Net', type: 'journal', status: 'posted', date: '2026-11-28', entityName: 'Payroll Net 2026-11', description: 'Monthly Payroll Run - Net Paid 2026-11', drAcc: '2100 Accrued Liabilities', crAcc: '1100 Bank Account', subtotal: '105300.00', total: '105300.00' }},
                {{ id: 'payroll_2026-11_Net', type: 'journal', status: 'posted', date: '2026-11-28', entityName: 'Payroll Net 2026-11', description: 'Monthly Payroll Run - Net Paid 2026-11', drAcc: '2100 Accrued Liabilities', crAcc: '1100 Bank Account', subtotal: '105300.00', total: '105300.00' }},
                {{ id: 'payroll_2026-10_Gross', type: 'journal', status: 'posted', date: '2026-10-28', entityName: 'Payroll Gross 2026-10', description: 'Monthly Payroll Run - Gross 2026-10', drAcc: '6500 Payroll / Salaries', crAcc: '2100 Accrued Liabilities', subtotal: '105300.00', total: '105300.00' }},
                {{ id: 'payroll_2026-10_Net', type: 'journal', status: 'posted', date: '2026-10-28', entityName: 'Payroll Net 2026-10', description: 'Monthly Payroll Run - Net Paid 2026-10', drAcc: '2100 Accrued Liabilities', crAcc: '1100 Bank Account', subtotal: '105300.00', total: '105300.00' }}
            ]),
            'payroll_2026-11': JSON.stringify({{
                paymentAccount: '1100 Bank Account',
                employees: {{ EMP001: {{ name: 'Joshel Celis', basic: '5,000.00', totalFixed: '5,300.00', daysWorked: 30, netPay: 5300 }} }}
            }}),
            'payroll_2026-10': JSON.stringify({{
                paymentAccount: '1100 Bank Account',
                employees: {{ EMP001: {{ name: 'Joshel Celis', basic: '5,000.00', totalFixed: '5,300.00', daysWorked: 30, netPay: 5300 }} }}
            }}),
            'bookkeeping_expenses': JSON.stringify([{{ id: 'EXP-0001', total: 100 }}]),
            'bookkeeping_bank_statements': JSON.stringify([{{ id: 'stmt-1', bankCode: '1005-1', closingBalance: 57850 }}]),
            'bookkeeping_cheques': JSON.stringify([{{ id: 'chq-1', chequeNumber: '123', amount: 50000 }}]),
            'bookkeeping_assets': JSON.stringify([{{ id: 'ast-1', description: 'Laptop', cost: 5000 }}]),
            'bookkeeping_accruals': JSON.stringify([{{ id: 'acc-1', description: 'Prepaid Rent', totalAmount: 12000 }}]),
            'bookkeeping_stock_ledger': JSON.stringify([{{ productName: 'Widget', qtyChange: 10 }}]),
            'bookkeeping_inventory': JSON.stringify([{{ name: 'Widget', qty: 10, price: 50 }}]),
            'bookkeeping_quotes': JSON.stringify([{{ id: 'q-1', quoteNum: 'QT-1001' }}]),
            'bookkeeping_pos': JSON.stringify([{{ id: 'po-1', poNum: 'PO-1001' }}]),
            'bookkeeping_recurring_v2': JSON.stringify([{{ id: 'rec-1', description: 'Monthly Retainer' }}]),
            'bookkeeping_closed_date': '2026-10-31',
            'bookkeeping_settings': JSON.stringify({{ companyName: 'Lumen Management Consultancy L.L.C FZ' }}),
            'bookkeeping_customers': JSON.stringify([{{ name: 'Joshel Celis' }}]),
            'bookkeeping_suppliers': JSON.stringify([{{ name: 'Meydan Free Zone' }}]),
            'bookkeeping_employees': JSON.stringify([{{ empId: 'EMP001', name: 'Joshel Celis' }}])
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
            id, value: '', innerHTML: '', textContent: '', style: {{}}, dataset: {{}},
            listeners: {{}},
            addEventListener(ev, fn) {{ this.listeners[ev] = fn; }},
            querySelector() {{ return null; }},
            querySelectorAll() {{ return []; }}
        }});
        ['clearHistoryBtn', 'historyTable', 'historyBody', 'emptyHistory', 'closeMonthDate'].forEach(id => {{
            elements[id] = makeEl(id);
        }});
        const documentMock = {{
            getElementById: (id) => elements[id] || makeEl(id),
            querySelector: () => null,
            querySelectorAll: () => [],
            createElement: (tag) => makeEl(tag),
            addEventListener() {{}}
        }};
        const windowMock = {{
            localStorage: localStorageMock, document: documentMock,
            LumenUI: {{ toast() {{}}, confirm: async () => true, validateFields: () => true }},
            LumenAttachments: {{ offload: (list) => list }},
            formatDateDdMmYy: (d) => String(d || ''),
            formatCurrency: (n) => Number(n || 0).toFixed(2)
        }};
        const context = vm.createContext({{
            window: windowMock, document: documentMock, localStorage: localStorageMock, console,
            CHART_OF_ACCOUNTS: [],
            historyTable: elements.historyTable, historyBody: elements.historyBody, emptyHistory: elements.emptyHistory,
            isLocked: () => false,
            getRawHistory: () => {{
                const list = JSON.parse(localStorageMock.getItem('bookkeeping_history_v2') || '[]');
                if (!windowMock.LumenPostingRepair) return list;
                const repaired = windowMock.LumenPostingRepair.repairEntry ? list.map(windowMock.LumenPostingRepair.repairEntry) : list;
                return windowMock.LumenPostingRepair.backfillSavedPayrolls ? windowMock.LumenPostingRepair.backfillSavedPayrolls(repaired) : repaired;
            }},
            getHistory: () => context.getRawHistory(),
            updateHistory: (list) => localStorageMock.setItem('bookkeeping_history_v2', JSON.stringify(list)),
            getInventory: () => JSON.parse(localStorageMock.getItem('bookkeeping_inventory') || '[]'),
            getStockLedger: () => JSON.parse(localStorageMock.getItem('bookkeeping_stock_ledger') || '[]'),
            getCustomers: () => JSON.parse(localStorageMock.getItem('bookkeeping_customers') || '[]'),
            getSuppliers: () => JSON.parse(localStorageMock.getItem('bookkeeping_suppliers') || '[]'),
            loadHistory: () => {{}}, loadInventory: () => {{}}, loadStockLedger: () => {{}},
            updateKPIs: () => {{}}, renderTrialBalance: () => {{}},
            safeNum: (v) => Number(v || 0).toFixed(2),
            escHtml: (s) => String(s ?? ''),
            formatCurrency: (n) => Number(n || 0).toFixed(2),
            Date, Math, Number, String, Object, Array, JSON, Map, Set, RegExp, parseFloat, parseInt, isNaN, isFinite
        }});
        vm.runInContext(fs.readFileSync({json.dumps(str(WEB_ROOT / "ar-posting-fix.js"))}, 'utf8'), context);
        vm.runInContext(fs.readFileSync({json.dumps(str(WEB_ROOT / "app-ledger-actions.js"))}, 'utf8'), context);
        vm.runInContext(fs.readFileSync({json.dumps(str(WEB_ROOT / "app-journals-and-coa.js"))}, 'utf8'), context);

        return (async () => {{
            const afterStartupHistory = context.getHistory();
            const net2026_11_count = afterStartupHistory.filter(e => e.id === 'payroll_2026-11_Net').length;

            await windowMock.deleteEntry('payroll_2026-10_Gross');
            const afterDelete2026_10 = context.getHistory().filter(e => String(e.entityName || '').includes('2026-10'));

            await elements.clearHistoryBtn.listeners.click();
            const afterClearHistory = context.getHistory();

            console.log(JSON.stringify({{
                net2026_11_count,
                afterDelete2026_10Count: afterDelete2026_10.length,
                afterClearHistoryCount: afterClearHistory.length,
                hasPayrollKeys: Object.keys(store).some(k => k.startsWith('payroll_')),
                expensesCount: JSON.parse(store['bookkeeping_expenses'] || '[]').length,
                bankStmtsCount: JSON.parse(store['bookkeeping_bank_statements'] || '[]').length,
                chequesCount: JSON.parse(store['bookkeeping_cheques'] || '[]').length,
                quotesCount: JSON.parse(store['bookkeeping_quotes'] || '[]').length,
                posCount: JSON.parse(store['bookkeeping_pos'] || '[]').length,
                recurringCount: JSON.parse(store['bookkeeping_recurring_v2'] || '[]').length,
                closedDate: store['bookkeeping_closed_date'] || null,
                inventoryQty: (JSON.parse(store['bookkeeping_inventory'] || '[]')[0] || {{}}).qty,
                preservedCompany: JSON.parse(store['bookkeeping_settings'] || '{{}}').companyName,
                preservedCustomers: JSON.parse(store['bookkeeping_customers'] || '[]').length,
                preservedSuppliers: JSON.parse(store['bookkeeping_suppliers'] || '[]').length,
                preservedEmployees: JSON.parse(store['bookkeeping_employees'] || '[]').length
            }}));
        }})();
        """
        result = run_node_script(script)
        self.assertEqual(result["net2026_11_count"], 1)
        self.assertEqual(result["afterDelete2026_10Count"], 0)
        self.assertEqual(result["afterClearHistoryCount"], 0)
        self.assertFalse(result["hasPayrollKeys"])
        self.assertEqual(result["expensesCount"], 0)
        self.assertEqual(result["bankStmtsCount"], 0)
        self.assertEqual(result["chequesCount"], 0)
        self.assertEqual(result["quotesCount"], 0)
        self.assertEqual(result["posCount"], 0)
        self.assertEqual(result["recurringCount"], 0)
        self.assertIsNone(result["closedDate"])
        self.assertEqual(result["inventoryQty"], 0)
        self.assertEqual(result["preservedCompany"], "Lumen Management Consultancy L.L.C FZ")
        self.assertEqual(result["preservedCustomers"], 1)
        self.assertEqual(result["preservedSuppliers"], 1)
        self.assertEqual(result["preservedEmployees"], 1)


if __name__ == "__main__":
    unittest.main()
