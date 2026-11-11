"""Unit and integration tests for UAE Peppol PINT-AE E-Invoicing ASP integration (Steps 1-4)."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from state_repository import LumenStateRepository
from tests.js_runner import run_node_script

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


class UAEPeppolAspIntegrationUnitTests(unittest.TestCase):
    """Verify Steps 1-4 of the UAE Peppol PINT-AE E-Invoicing ASP integration (Marmin AI default + multi-provider)."""

    def test_step1_customer_trade_license_and_pint_ae_ibr_150_ae_legal_entity(self) -> None:
        index_html = _read_index_html_bundle()
        script_bundle = _read_script_js_bundle()
        self.assertIn('id="dirCustTradeLicense"', index_html)
        self.assertIn("dirCustTradeLicense", script_bundle)

        node_script = """
const assert = require('assert');
const path = require('path');
const EInvoiceAE = require(path.join(process.env.APP_DIR, 'einvoice-ae.js'));

const settings = {
    companyName: 'Lumen Consultancy LLC',
    trnNumber: '100123456700003',
    tradeLicenseNumber: 'DED-884210',
    companyAddress: 'Business Bay, Dubai, UAE',
    emirate: 'Dubai'
};
const custProfile = {
    name: 'Al Noor Trading LLC',
    trn: '100987654300003',
    tradeLicense: 'TL-99102',
    address: 'Al Maryah Island, Abu Dhabi, UAE',
    emirate: 'Abu Dhabi'
};
const entry = {
    id: 'inv-step1',
    type: 'customer',
    invoiceNum: 'INV-2026-501',
    date: '2026-11-10',
    dueDate: '2026-12-10',
    entityName: 'Al Noor Trading LLC',
    trn: '100987654300003',
    subtotal: '1000.00',
    tax: '50.00',
    total: '1050.00',
    vatTreatment: 'standard',
    items: [{ description: 'Advisory Retainer', qty: 1, rate: 1000, amount: 1000, tax: 50, vatCategory: 'S', vatRate: 5 }]
};

const xml = EInvoiceAE.buildXml(entry, settings, custProfile);
assert(xml.includes('<cbc:EndpointID schemeID="0235">1001234567</cbc:EndpointID>'));
assert(xml.includes('<cbc:EndpointID schemeID="0235">1009876543</cbc:EndpointID>'));
assert(xml.includes('<cbc:CompanyID schemeID="0235">DED-884210</cbc:CompanyID>'));
assert(xml.includes('<cbc:CompanyID schemeID="0235">TL-99102</cbc:CompanyID>'));
console.log(JSON.stringify({ status: 'ok' }));
"""
        proc = run_node_script(node_script, APP_DIR)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_step2_settings_multi_provider_asp_connection_card(self) -> None:
        index_html = _read_index_html_bundle()
        script_bundle = _read_script_js_bundle()
        for dom_id in (
            "einvoiceAspSettingsCard",
            "settingAspProvider",
            "settingAspEnvironment",
            "settingAspApiKey",
            "settingAspProfileId",
            "settingAspEndpointUrl",
            "settingAspAutoTransmit",
            "btnSaveEinvoiceSettings",
        ):
            self.assertIn(f'id="{dom_id}"', index_html)
        for provider_opt in (
            '<option value="marmin">',
            '<option value="invoicenow">',
            '<option value="flick">',
            '<option value="cleartax">',
            '<option value="custom">',
        ):
            self.assertIn(provider_opt, index_html)
        self.assertIn("saveEinvoiceSettings", script_bundle)

    def test_step3_and_step4_einvoice_transmit_webhook_and_inbound_peppol_xml(self) -> None:
        node_script = """
const assert = require('assert');
const path = require('path');
const EInvoiceAE = require(path.join(process.env.APP_DIR, 'einvoice-ae.js'));

assert(EInvoiceAE.PROVIDERS && EInvoiceAE.PROVIDERS.marmin);
assert.strictEqual(EInvoiceAE.PROVIDERS.marmin.accreditationNo, '160945');
assert(EInvoiceAE.PROVIDERS.invoicenow && EInvoiceAE.PROVIDERS.flick && EInvoiceAE.PROVIDERS.cleartax);
assert.strictEqual(typeof EInvoiceAE.transmit, 'function');
assert.strictEqual(typeof EInvoiceAE.parseInboundXml, 'function');

const settings = {
    companyName: 'Lumen Consultancy LLC',
    trnNumber: '100123456700003',
    tradeLicenseNumber: 'DED-884210',
    companyAddress: 'Business Bay, Dubai, UAE',
    emirate: 'Dubai',
    aspProvider: 'marmin',
    aspEnvironment: 'sandbox'
};
const custProfile = {
    name: 'Emirates Retail LLC',
    trn: '100555555500003',
    tradeLicense: 'CN-441122',
    address: 'Sheikh Zayed Road, Dubai, UAE',
    emirate: 'Dubai'
};
const sampleEntry = {
    id: 'inv-step3',
    type: 'customer',
    invoiceNum: 'INV-2026-777',
    date: '2026-11-11',
    dueDate: '2026-12-11',
    entityName: 'Emirates Retail LLC',
    trn: '100555555500003',
    subtotal: '2000.00',
    tax: '100.00',
    total: '2100.00',
    vatTreatment: 'standard',
    items: [{ description: 'Cloud ERP Implementation', qty: 2, rate: 1000, amount: 2000, tax: 100, vatCategory: 'S', vatRate: 5 }]
};

const xml = EInvoiceAE.buildXml(sampleEntry, settings, custProfile);
const parsedInbound = EInvoiceAE.parseInboundXml(xml);
assert.strictEqual(parsedInbound.ok, true);
assert.strictEqual(parsedInbound.entry.type, 'supplier');
assert.strictEqual(parsedInbound.entry.invoiceNum, 'INV-2026-777');
assert.strictEqual(parsedInbound.entry.entityName, 'Lumen Consultancy LLC');
assert.strictEqual(parsedInbound.entry.trn, '100123456700003');
assert.strictEqual(parsedInbound.entry.tradeLicense, 'DED-884210');
assert.strictEqual(parsedInbound.entry.subtotal, '2000.00');
assert.strictEqual(parsedInbound.entry.tax, '100.00');
assert.strictEqual(parsedInbound.entry.total, '2100.00');
assert.strictEqual(parsedInbound.entry.einvoiceStatus, 'RECEIVED_PEPPOL');
assert.strictEqual(parsedInbound.entry.trnVerified, true);
assert.strictEqual(parsedInbound.entry.items.length, 1);

console.log(JSON.stringify({ status: 'ok', xml }));
"""
        proc = run_node_script(node_script, APP_DIR)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = json.loads(proc.stdout.strip().splitlines()[-1])
        sample_xml = out["xml"]

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = LumenStateRepository(Path(tmpdir) / "einvoice_test.sqlite3")
            repo.mutate_state({
                "lumen_profiles": json.dumps([{"id": "prof-1", "name": "Lumen LLC", "accountId": "owner"}]),
                "profile:prof-1::bookkeeping_history_v2": json.dumps([
                    {
                        "id": "inv-step3",
                        "type": "customer",
                        "invoiceNum": "INV-2026-777",
                        "date": "2026-11-11",
                        "entityName": "Emirates Retail LLC",
                        "trn": "100555555500003",
                        "subtotal": "2000.00",
                        "tax": "100.00",
                        "total": "2100.00",
                    }
                ]),
            })
            submit_res = repo.submit_einvoice(
                {
                    "profileId": "prof-1",
                    "invoiceId": "inv-step3",
                    "invoiceNum": "INV-2026-777",
                    "provider": "marmin",
                    "environment": "sandbox",
                    "xml": sample_xml,
                },
                caller_account="owner",
            )
            self.assertTrue(submit_res.get("ok"), submit_res)
            self.assertEqual(submit_res.get("einvoiceStatus"), "SANDBOX_CLEARED")
            self.assertEqual(submit_res.get("einvoiceProvider"), "marmin")
            self.assertEqual(submit_res.get("accreditationNo"), "160945")
            self.assertTrue(submit_res.get("einvoiceUuid"))

            flick_res = repo.submit_einvoice(
                {
                    "profileId": "prof-1",
                    "invoiceId": "inv-step3",
                    "invoiceNum": "INV-2026-777",
                    "provider": "flick",
                    "environment": "sandbox",
                    "xml": sample_xml,
                },
                caller_account="owner",
            )
            self.assertTrue(flick_res.get("ok"), flick_res)
            self.assertEqual(flick_res.get("einvoiceProvider"), "flick")
            self.assertEqual(flick_res.get("accreditationNo"), "138271")

            webhook_res = repo.handle_einvoice_webhook(
                {
                    "profileId": "prof-1",
                    "invoiceId": "inv-step3",
                    "einvoiceUuid": flick_res["einvoiceUuid"],
                    "status": "FTA_CLEARED",
                }
            )
            self.assertTrue(webhook_res.get("ok"), webhook_res)
            updated_hist = json.loads(repo.get_all_state()["profile:prof-1::bookkeeping_history_v2"])
            self.assertEqual(updated_hist[0]["einvoiceStatus"], "FTA_CLEARED")

            inbound_res = repo.receive_inbound_einvoice(
                {
                    "profileId": "prof-1",
                    "xml": sample_xml,
                },
                caller_account="owner",
            )
            self.assertTrue(inbound_res.get("ok"), inbound_res)
            self.assertEqual(inbound_res["entry"]["type"], "supplier")
            self.assertEqual(inbound_res["entry"]["einvoiceStatus"], "RECEIVED_PEPPOL")
            self.assertTrue(inbound_res["entry"]["trnVerifiedAt"])


if __name__ == "__main__":
    unittest.main()
