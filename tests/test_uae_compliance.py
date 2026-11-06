"""Unit and behavioral Node.js tests for the UAE Compliance Reminder widget (`compliance-reminders.js`)."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import unittest

REPO_ROOT = Path(__file__).resolve().parent.parent
APP_DIR = REPO_ROOT.parent / "bookkeeping-tool"


def _read_index_html_bundle() -> str:
    parts = [(APP_DIR / "index.html").read_text(encoding="utf-8")]
    for path in sorted(APP_DIR.glob("views-*.js")):
        parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)


def _read_script_js_bundle() -> str:
    parts = [(APP_DIR / "script.js").read_text(encoding="utf-8")]
    for path in sorted(APP_DIR.glob("app-*.js")):
        parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)


class UAEComplianceRemindersUnitTests(unittest.TestCase):
    """Verify the Home Dashboard UAE Compliance Reminder widget, Settings fields, and Employee Visa/EID fields."""

    def test_index_html_and_views_wire_compliance_reminder_card_and_inputs(self) -> None:
        index_bundle = _read_index_html_bundle()
        reminder_js_path = APP_DIR / "compliance-reminders.js"

        self.assertTrue(
            reminder_js_path.is_file(),
            "compliance-reminders.js must exist in bookkeeping-tool",
        )
        self.assertIn("compliance-reminders.js", index_bundle)

        for dom_id in (
            "uaeComplianceReminderCard",
            "complianceOverallBadge",
            "compTradeLicenseBadge",
            "compTradeLicenseExpiry",
            "compTradeLicenseRef",
            "compEstCardBadge",
            "compEstCardExpiry",
            "compEstCardRef",
            "compEmployeeAlertsBadge",
            "compEmployeeAlertsList",
            "settingTradeLicenseNumber",
            "settingTradeLicenseExpiry",
            "settingEstablishmentCardNumber",
            "settingEstablishmentCardExpiry",
            "dirEmpVisaExpiry",
            "dirEmpEmiratesIdExpiry",
        ):
            self.assertIn(f'id="{dom_id}"', index_bundle)

    def test_compliance_reminders_is_wired_to_dashboard_settings_and_employees(self) -> None:
        reminder_js_path = APP_DIR / "compliance-reminders.js"
        self.assertTrue(
            reminder_js_path.is_file(),
            "compliance-reminders.js must exist in bookkeeping-tool",
        )
        reminder_js = reminder_js_path.read_text(encoding="utf-8")
        script_bundle = _read_script_js_bundle()

        for sym in (
            "UAEComplianceReminders",
            "evaluate",
            "renderWidget",
            "URGENT_THRESHOLD_DAYS",
            "WARNING_THRESHOLD_DAYS",
        ):
            self.assertIn(sym, reminder_js)

        self.assertIn("UAEComplianceReminders.renderWidget", script_bundle)
        for field_id in (
            "settingTradeLicenseExpiry",
            "settingEstablishmentCardExpiry",
            "dirEmpVisaExpiry",
            "dirEmpEmiratesIdExpiry",
        ):
            self.assertIn(field_id, script_bundle)
        payroll_js = (APP_DIR / "app-payroll-and-wps.js").read_text(encoding="utf-8")
        self.assertIn("escHtml(e.visaExpiry)", payroll_js)
        self.assertIn("escHtml(e.emiratesIdExpiry)", payroll_js)
        self.assertIn("escHtml(e.name", payroll_js)

    def test_compliance_reminders_executes_behaviorally_in_node(self) -> None:
        node_script = r"""
const assert = require('assert');
const path = require('path');
const appDir = process.env.APP_DIR;

const store = {};
global.localStorage = {
    getItem: (k) => (k in store ? store[k] : null),
    setItem: (k, v) => { store[k] = String(v); },
    removeItem: (k) => { delete store[k]; }
};
const elements = {};
global.document = {
    getElementById: (id) => {
        if (!elements[id]) elements[id] = { textContent: '', innerHTML: '', className: '', style: {} };
        return elements[id];
    }
};
global.window = {
    localStorage: global.localStorage,
    document: global.document
};

const UAEComplianceReminders = require(path.join(appDir, 'compliance-reminders.js'));

// 1. Unconfigured state
const emptyEval = UAEComplianceReminders.evaluate({
    settings: {},
    employees: [],
    referenceDate: '2026-11-05'
});
assert.strictEqual(emptyEval.overallStatus, 'setup_needed');
assert.strictEqual(emptyEval.tradeLicense.status, 'not_set');
assert.strictEqual(emptyEval.establishmentCard.status, 'not_set');

// 2. Mixed urgent / expired / warning / valid state
const mixedEval = UAEComplianceReminders.evaluate({
    settings: {
        companyName: 'Lumen Trading LLC',
        tradeLicenseNumber: 'DED-778899',
        tradeLicenseExpiry: '2026-10-31', // 5 days expired relative to 2026-11-05
        establishmentCardNumber: 'MOHRE-112233',
        establishmentCardExpiry: '2026-11-25' // 20 days remaining (<= 30d urgent)
    },
    employees: [
        {
            empId: 'EMP001',
            name: 'Omar Al Mansoori',
            visaExpiry: '2026-12-20', // 45 days remaining (<= 60d warning)
            emiratesIdExpiry: '2027-06-01' // > 60d valid
        },
        {
            empId: 'EMP002',
            name: 'Sara Khan',
            visaExpiry: '2026-10-26', // 10 days expired
            emiratesIdExpiry: '2026-11-20' // 15 days remaining (<= 30d urgent)
        }
    ],
    referenceDate: '2026-11-05'
});

assert.strictEqual(mixedEval.tradeLicense.status, 'expired');
assert.strictEqual(mixedEval.tradeLicense.daysRemaining, -5);
assert.strictEqual(mixedEval.establishmentCard.status, 'expiring_30');
assert.strictEqual(mixedEval.establishmentCard.daysRemaining, 20);
assert.strictEqual(mixedEval.expiredCount, 2); // Trade License + Sara Visa
assert.strictEqual(mixedEval.urgent30Count, 2); // Est Card + Sara EID
assert.strictEqual(mixedEval.warning60Count, 1); // Omar Visa
assert.strictEqual(mixedEval.validCount, 1); // Omar EID
assert.strictEqual(mixedEval.employeeAlertsCount, 3); // Sara Visa, Sara EID, Omar Visa
assert.strictEqual(mixedEval.overallStatus, 'action_required');

// 3. All compliant state
const compliantEval = UAEComplianceReminders.evaluate({
    settings: {
        tradeLicenseNumber: 'DED-778899',
        tradeLicenseExpiry: '2027-08-15',
        establishmentCardNumber: 'MOHRE-112233',
        establishmentCardExpiry: '2027-09-01'
    },
    employees: [
        {
            empId: 'EMP001',
            name: 'Omar Al Mansoori',
            visaExpiry: '2027-10-10',
            emiratesIdExpiry: '2027-10-10'
        }
    ],
    referenceDate: '2026-11-05'
});
assert.strictEqual(compliantEval.overallStatus, 'all_compliant');
assert.strictEqual(compliantEval.expiredCount, 0);
assert.strictEqual(compliantEval.urgent30Count, 0);
assert.strictEqual(compliantEval.warning60Count, 0);
assert.strictEqual(compliantEval.employeeAlertsCount, 0);

// 4. DOM rendering verification with XSS escaping
store['bookkeeping_settings'] = JSON.stringify({
    tradeLicenseNumber: 'CN-9001',
    tradeLicenseExpiry: '2026-11-20',
    establishmentCardNumber: 'EST-5001',
    establishmentCardExpiry: '2027-05-01'
});
store['bookkeeping_employees'] = JSON.stringify([
    {
        empId: 'EMP001',
        name: 'Tariq <script>evil()</script>',
        visaExpiry: '2026-11-15',
        emiratesIdExpiry: '2027-08-01'
    }
]);
UAEComplianceReminders.renderWidget({ referenceDate: '2026-11-05' });
assert(elements['compTradeLicenseBadge'].textContent.includes('15d'));
assert.strictEqual(elements['compTradeLicenseExpiry'].textContent, '2026-11-20');
assert(elements['compEstCardBadge'].textContent.includes('Valid'));
assert(!elements['compEmployeeAlertsList'].innerHTML.includes('<script>evil()</script>'));
assert(elements['compEmployeeAlertsList'].innerHTML.includes('&lt;script&gt;evil()&lt;/script&gt;'));

console.log(JSON.stringify({ status: 'ok' }));
"""
        from tests.js_runner import run_node_script

        proc = run_node_script(node_script, APP_DIR)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout.strip().splitlines()[-1])
        self.assertEqual(payload["status"], "ok")


class UAEWpsAndGratuityUnitTests(unittest.TestCase):
    """Verify the Enhanced UAE WPS .SIF Generator (MOHRE SCR + EDR) & Tenure-Aware 21/30-Day Statutory Gratuity Calculator."""

    def test_index_html_and_views_wire_wps_gratuity_module_and_scr_controls(self) -> None:
        index_bundle = _read_index_html_bundle()
        script_bundle = _read_script_js_bundle()
        wps_js_path = APP_DIR / "wps-gratuity.js"

        self.assertTrue(
            wps_js_path.is_file(),
            "wps-gratuity.js must exist in bookkeeping-tool",
        )
        self.assertIn("wps-gratuity.js", index_bundle)

        for dom_id in (
            "settingWpsEmployerId",
            "settingWpsBankRoutingCode",
            "settingWpsEmployerRef",
            "wpsEmployerId",
            "wpsEmployerRoutingCode",
            "wpsEmployerRef",
            "btnPreviewWpsSif",
            "wpsSifPreviewBox",
            "eosbSummaryContainer",
        ):
            self.assertIn(f'id="{dom_id}"', index_bundle)

        self.assertIn("UAEWpsAndGratuity", script_bundle)
        settings_kpis_js = (APP_DIR / "app-settings-and-kpis.js").read_text(encoding="utf-8")
        payroll_wps_js = (APP_DIR / "app-payroll-and-wps.js").read_text(encoding="utf-8")
        self.assertIn("Number.isFinite(parsedDaysWorked) ? parsedDaysWorked : 30", settings_kpis_js)
        self.assertIn("Number.isFinite(parsedDays) ? parsedDays : 30", payroll_wps_js)

    def test_wps_and_gratuity_executes_behaviorally_in_node(self) -> None:
        node_script = r"""
const assert = require('assert');
const path = require('path');
const appDir = process.env.APP_DIR;

const UAEWpsAndGratuity = require(path.join(appDir, 'wps-gratuity.js'));

// 1. < 1 Year Tenure (Probation / Pre-Eligibility: 0 statutory termination entitlement, 21d/yr accounting accrual)
const subYear = UAEWpsAndGratuity.calculateEmployeeGratuity({
    basicSalary: 12000,
    totalPay: 15000,
    dateHired: '2026-05-09',
    asOfDate: '2026-11-05', // 180 days (< 1 year)
    unpaidLeaveDays: 0
});
assert.strictEqual(subYear.bracket, 'under_1_year');
assert.strictEqual(subYear.dailyRateDays, 21);
assert.strictEqual(subYear.statutoryGratuity, 0);
assert.strictEqual(subYear.monthlyAccrual, 700); // (12000 / 30) * (21 / 12) = 400 * 1.75 = 700
assert(subYear.accountingProvision > 0);

// 2. 1 to 5 Years Tenure (21 days basic salary per year)
const tier1Emp = UAEWpsAndGratuity.calculateEmployeeGratuity({
    basicSalary: 15000,
    totalPay: 20000,
    dateHired: '2023-11-06',
    asOfDate: '2026-11-05', // 1095 days = 3.00 years
    unpaidLeaveDays: 0
});
assert.strictEqual(tier1Emp.bracket, 'years_1_to_5');
assert.strictEqual(tier1Emp.dailyRateDays, 21);
assert.strictEqual(Math.round(tier1Emp.serviceYears * 100) / 100, 3);
assert.strictEqual(Math.round(tier1Emp.tier1Gratuity * 100) / 100, 31500); // (15000/30) * 21 * 3
assert.strictEqual(tier1Emp.tier2Gratuity, 0);
assert.strictEqual(Math.round(tier1Emp.statutoryGratuity * 100) / 100, 31500);
assert.strictEqual(tier1Emp.monthlyAccrual, 875); // (15000/30) * (21/12)

// 3. > 5 Years Tenure (21 days/yr for first 5 years + 30 days/yr for years beyond 5)
const tier2Emp = UAEWpsAndGratuity.calculateEmployeeGratuity({
    basicSalary: 12000,
    totalPay: 16000,
    dateHired: '2019-11-07',
    asOfDate: '2026-11-05', // 2555 days = 7.00 years
    unpaidLeaveDays: 0
});
assert.strictEqual(tier2Emp.bracket, 'over_5_years');
assert.strictEqual(tier2Emp.dailyRateDays, 30);
assert.strictEqual(Math.round(tier2Emp.serviceYears * 100) / 100, 7);
assert.strictEqual(Math.round(tier2Emp.tier1Gratuity * 100) / 100, 42000); // (12000/30) * 21 * 5 = 42000
assert.strictEqual(Math.round(tier2Emp.tier2Gratuity * 100) / 100, 24000); // (12000/30) * 30 * 2 = 24000
assert.strictEqual(Math.round(tier2Emp.statutoryGratuity * 100) / 100, 66000);
assert.strictEqual(tier2Emp.monthlyAccrual, 1000); // (12000/30) * (30/12) = 400 * 2.5 = 1000

// 4. Unpaid leave days excluded from service tenure (UAE Labour Law Art. 51(4))
const unpaidAdj = UAEWpsAndGratuity.calculateEmployeeGratuity({
    basicSalary: 12000,
    totalPay: 15000,
    dateHired: '2021-10-27',
    asOfDate: '2026-11-05', // 1835 calendar days
    unpaidLeaveDays: 10 // 1825 effective days = 5.00 years
});
assert.strictEqual(unpaidAdj.effectiveServiceDays, 1825);
assert.strictEqual(Math.round(unpaidAdj.serviceYears * 100) / 100, 5);
assert.strictEqual(Math.round(unpaidAdj.statutoryGratuity * 100) / 100, 42000);

// 5. 2-Year Total Wage Cap (UAE Labour Law Art. 51(2))
const cappedEmp = UAEWpsAndGratuity.calculateEmployeeGratuity({
    basicSalary: 15000,
    totalPay: 15000,
    dateHired: '1996-11-12',
    asOfDate: '2026-11-05', // 10950 days = 30 years
    unpaidLeaveDays: 0
});
assert.strictEqual(cappedEmp.isCapped, true);
assert.strictEqual(cappedEmp.maxGratuityCap, 360000); // 24 * 15000
assert.strictEqual(cappedEmp.statutoryGratuity, 360000);

// 6. MOHRE WPS .SIF Generator (EDR + SCR header/control record)
const sifRes = UAEWpsAndGratuity.buildWpsSif({
    period: '2026-10',
    creationDate: '2026-10-28',
    creationTime: '1430',
    settings: {
        wpsEmployerId: '1002233445566',
        wpsBankRoutingCode: '302620122',
        wpsEmployerRef: 'WPS-LUMEN-202610'
    },
    records: [
        {
            empId: 'EMP001',
            name: 'Tariq Al Mansoori',
            labourCard: '78419901234567',
            routingCode: '302620122',
            iban: 'AE07 0331 2345 6789 0123 456',
            basicSalary: 15000,
            totalPay: 20000,
            daysWorked: 30,
            bonus: 1500,
            loanDed: 0,
            deductions: 0,
            netPay: 21500
        },
        {
            empId: 'EMP002',
            name: 'Sara Khan',
            labourCard: '98765432',
            routingCode: '033120101',
            iban: 'AE250260001012345678901',
            basicSalary: 10500,
            totalPay: 15000,
            daysWorked: 28,
            bonus: 0,
            loanDed: 0,
            deductions: 0,
            netPay: 14000
        }
    ]
});

assert.strictEqual(sifRes.edrCount, 2);
assert.strictEqual(sifRes.totalSalary, 35500);
assert.strictEqual(sifRes.salaryMonth, '102026');
assert.strictEqual(sifRes.payStartDate, '2026-10-01');
assert.strictEqual(sifRes.payEndDate, '2026-10-31');
assert.strictEqual(
    sifRes.edrLines[0],
    'EDR,78419901234567,302620122,AE070331234567890123456,2026-10-01,2026-10-31,30,20000.00,1500.00,0'
);
assert.strictEqual(
    sifRes.edrLines[1],
    'EDR,00000098765432,033120101,AE250260001012345678901,2026-10-01,2026-10-31,28,14000.00,0.00,2'
);
assert.strictEqual(
    sifRes.scrLine,
    'SCR,1002233445566,302620122,2026-10-28,1430,102026,2,35500.00,AED,WPS-LUMEN-202610'
);
assert(sifRes.sifContent.includes(sifRes.edrLines[0]));
assert(sifRes.sifContent.includes(sifRes.scrLine));

console.log(JSON.stringify({ status: 'ok' }));
"""
        from tests.js_runner import run_node_script

        proc = run_node_script(node_script, APP_DIR)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout.strip().splitlines()[-1])
        self.assertEqual(payload["status"], "ok")


if __name__ == "__main__":
    unittest.main()
