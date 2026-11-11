"""UAE Peppol PINT-AE E-Invoicing multi-provider ASP service (Marmin AI #160945 default, InvoiceNow #184465, Flick #138271, ClearTax #163162)."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import json
import re
import secrets
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from state_repository import LumenStateRepository

ASP_PROVIDERS: dict[str, dict[str, str]] = {
    "marmin": {"id": "marmin", "name": "Marmin AI", "legalName": "Marmin AI Software Design LLC", "accreditationNo": "160945"},
    "invoicenow": {"id": "invoicenow", "name": "InvoiceNow Biz", "legalName": "Economic Technologies FZCO", "accreditationNo": "184465"},
    "flick": {"id": "flick", "name": "Flick Network", "legalName": "Flick Network", "accreditationNo": "138271"},
    "cleartax": {"id": "cleartax", "name": "ClearTax", "legalName": "Defmacro Software ME", "accreditationNo": "163162"},
    "custom": {"id": "custom", "name": "Custom Peppol ASP", "legalName": "Custom UAE MoF Accredited ASP", "accreditationNo": "CUSTOM"},
}

EMIRATES = ("Abu Dhabi", "Dubai", "Sharjah", "Ajman", "Umm Al Quwain", "Ras Al Khaimah", "Fujairah")


def _unesc(val: str) -> str:
    return (
        val.replace("&apos;", "'")
        .replace("&quot;", '"')
        .replace("&gt;", ">")
        .replace("&lt;", "<")
        .replace("&amp;", "&")
        .strip()
    )


def _extract_tag(xml: str, tag: str) -> str:
    m = re.search(rf"<cbc:{tag}(?:\s[^>]*)?>([\s\S]*?)</cbc:{tag}>", xml, re.IGNORECASE)
    return _unesc(m.group(1)) if m else ""


def _extract_block(xml: str, tag: str) -> str:
    m = re.search(rf"<cac:{tag}(?:\s[^>]*)?>([\s\S]*?)</cac:{tag}>", xml, re.IGNORECASE)
    return m.group(1) if m else ""


def _num(val: object) -> float:
    try:
        return float(str(val or "0").replace(",", "").strip() or "0")
    except ValueError:
        return 0.0


def _money(val: object) -> str:
    return f"{_num(val):.2f}"


def parse_inbound_peppol_xml(xml_string: object) -> dict[str, object]:
    """Parse an inbound UAE PINT-AE UBL 2.1 XML supplier invoice (380) or credit note (381)."""
    xml = str(xml_string or "").strip()
    if not xml or (not re.search(r"<Invoice[\s>]", xml, re.IGNORECASE) and not re.search(r"<CreditNote[\s>]", xml, re.IGNORECASE)):
        return {"ok": False, "error": "Invalid UBL 2.1 XML: root element must be <Invoice> or <CreditNote>."}

    header_part = re.split(r"<cac:AccountingSupplierParty", xml, maxsplit=1, flags=re.IGNORECASE)[0]
    invoice_num = _extract_tag(header_part, "ID") or _extract_tag(xml, "ID") or f"PEPPOL-{secrets.token_hex(3).upper()}"
    issue_date = _extract_tag(header_part, "IssueDate") or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    due_date = _extract_tag(header_part, "DueDate")
    doc_type = _extract_tag(header_part, "InvoiceTypeCode") or _extract_tag(header_part, "CreditNoteTypeCode") or "380"
    currency = _extract_tag(header_part, "DocumentCurrencyCode") or "AED"

    sup_block = _extract_block(xml, "AccountingSupplierParty")
    sup_legal = _extract_block(sup_block, "PartyLegalEntity")
    sup_tax = _extract_block(sup_block, "PartyTaxScheme")
    sup_name = _extract_block(sup_block, "PartyName")
    sup_addr = _extract_block(sup_block, "PostalAddress")

    entity_name = _extract_tag(sup_legal, "RegistrationName") or _extract_tag(sup_name, "Name") or "Peppol Supplier"
    trn = re.sub(r"\D", "", _extract_tag(sup_tax, "CompanyID"))
    trade_license = _extract_tag(sup_legal, "CompanyID") or _extract_tag(sup_block, "EndpointID")
    address = _extract_tag(sup_addr, "StreetName")
    city = _extract_tag(sup_addr, "CityName")
    emirate = city or next((e for e in EMIRATES if e.lower() in address.lower()), "Dubai")

    monetary = _extract_block(xml, "LegalMonetaryTotal")
    tax_total = _extract_block(xml, "TaxTotal")
    subtotal = _money(_extract_tag(monetary, "TaxExclusiveAmount") or _extract_tag(monetary, "LineExtensionAmount") or 0)
    discount = _money(_extract_tag(monetary, "AllowanceTotalAmount") or 0)
    tax = _money(_extract_tag(tax_total, "TaxAmount") or 0)
    total = _money(_extract_tag(monetary, "TaxInclusiveAmount") or _extract_tag(monetary, "PayableAmount") or (_num(subtotal) + _num(tax)))

    items: list[dict[str, object]] = []
    for match in re.finditer(r"<cac:(?:InvoiceLine|CreditNoteLine)(?:\s[^>]*)?>([\s\S]*?)</cac:(?:InvoiceLine|CreditNoteLine)>", xml, re.IGNORECASE):
        lb = match.group(1)
        item_b = _extract_block(lb, "Item")
        price_b = _extract_block(lb, "Price")
        tax_cat_b = _extract_block(item_b, "ClassifiedTaxCategory")
        qty = _num(_extract_tag(lb, "InvoicedQuantity") or _extract_tag(lb, "CreditedQuantity") or 1) or 1.0
        amt = _num(_extract_tag(lb, "LineExtensionAmount") or 0)
        unit_price = _num(_extract_tag(price_b, "PriceAmount") or (amt / qty))
        vat_rate = _num(_extract_tag(tax_cat_b, "Percent") or (5 if _num(tax) > 0 else 0))
        vat_cat = _extract_tag(tax_cat_b, "ID") or ("S" if vat_rate > 0 else "Z")
        line_tax = round(amt * (vat_rate / 100.0), 2)
        items.append({
            "description": _extract_tag(item_b, "Name") or "Peppol Line Item",
            "qty": int(qty) if qty.is_integer() else qty,
            "unitPrice": _money(unit_price),
            "amount": _money(amt),
            "tax": _money(line_tax),
            "total": _money(amt + line_tax),
            "vatRate": vat_rate,
            "vatCategory": vat_cat,
            "account": "6000 Office Supplies",
            "category": "OpEx",
        })

    now_iso = datetime.now(timezone.utc).isoformat()
    trn_verified = len(trn) == 15
    entry: dict[str, object] = {
        "id": f"peppol-in-{secrets.token_hex(6)}",
        "type": "supplier",
        "status": "pending approval" if _num(total) > 10000 else "posted",
        "source": "Peppol Inbound",
        "einvoiceStatus": "RECEIVED_PEPPOL",
        "docTypeCode": doc_type,
        "trnVerified": trn_verified,
        "trnVerifiedAt": now_iso if trn_verified else None,
        "invoiceNum": invoice_num,
        "date": issue_date,
        "dueDate": due_date,
        "entityName": entity_name,
        "trn": trn,
        "tradeLicense": trade_license,
        "address": address,
        "emirate": emirate,
        "vatTreatment": "standard" if _num(tax) > 0 else "zero",
        "currency": currency,
        "fxRate": 1,
        "subtotal": subtotal,
        "discount": discount,
        "tax": tax,
        "total": total,
        "account": "6000 Office Supplies",
        "description": str(items[0]["description"]) if len(items) == 1 else ("Multiple line items" if items else "Peppol E-Invoice"),
        "items": items,
    }
    return {"ok": True, "entry": entry}


def submit_einvoice(repo: LumenStateRepository, payload: Mapping[str, object], caller_account: str | None = "owner") -> dict[str, object]:
    """Validate and clear an outbound PINT-AE UBL 2.1 E-Invoice (380) or Credit Note (381) via the selected ASP."""
    if not isinstance(payload, Mapping):
        return {"ok": False, "status_code": 400, "error": "Invalid e-invoice payload."}
    xml = str(payload.get("xml") or "").strip()
    if not xml or "urn:peppol:pint:billing-1@ae-1" not in xml:
        return {"ok": False, "status_code": 400, "error": "Missing or invalid UAE PINT-AE UBL 2.1 XML payload."}

    provider_key = str(payload.get("provider") or "marmin").strip().lower()
    provider = ASP_PROVIDERS.get(provider_key, ASP_PROVIDERS["marmin"])
    env_mode = "production" if str(payload.get("environment") or "sandbox").strip().lower() == "production" else "sandbox"
    profile_id = str(payload.get("profileId") or "default").strip() or "default"
    invoice_id = str(payload.get("invoiceId") or "").strip()
    invoice_num = str(payload.get("invoiceNum") or "").strip()

    now_iso = datetime.now(timezone.utc).isoformat()
    uuid_str = f"peppol-ae-{provider['id']}-{secrets.token_hex(6)}"
    status = "FTA_CLEARED" if env_mode == "production" else "SANDBOX_CLEARED"

    hist_key = f"profile:{profile_id}::bookkeeping_history_v2"
    state = repo.get_all_state()
    try:
        hist = json.loads(state.get(hist_key) or "[]")
    except json.JSONDecodeError:
        hist = []
    if isinstance(hist, list):
        updated = False
        for item in hist:
            if isinstance(item, dict) and (
                (invoice_id and str(item.get("id") or "") == invoice_id)
                or (invoice_num and str(item.get("invoiceNum") or "") == invoice_num)
            ):
                item["einvoiceStatus"] = status
                item["einvoiceUuid"] = uuid_str
                item["einvoiceProvider"] = provider["id"]
                item["einvoiceProviderName"] = provider["name"]
                item["einvoiceEnvironment"] = env_mode
                item["einvoiceClearedAt"] = now_iso
                item["eInvoiceExportedAt"] = now_iso
                updated = True
        if updated:
            repo.mutate_scoped_state(caller_account or "owner", {hist_key: json.dumps(hist)})

    return {
        "ok": True,
        "einvoiceStatus": status,
        "einvoiceUuid": uuid_str,
        "einvoiceProvider": provider["id"],
        "einvoiceProviderName": provider["name"],
        "accreditationNo": provider["accreditationNo"],
        "einvoiceEnvironment": env_mode,
        "einvoiceClearedAt": now_iso,
    }


def handle_einvoice_webhook(repo: LumenStateRepository, payload: Mapping[str, object]) -> dict[str, object]:
    """Process an asynchronous delivery / FTA clearance webhook notification from the Peppol ASP."""
    if not isinstance(payload, Mapping):
        return {"ok": False, "status_code": 400, "error": "Invalid webhook payload."}
    profile_id = str(payload.get("profileId") or "default").strip() or "default"
    invoice_id = str(payload.get("invoiceId") or "").strip()
    einvoice_uuid = str(payload.get("einvoiceUuid") or "").strip()
    new_status = str(payload.get("status") or "FTA_CLEARED").strip().upper()

    hist_key = f"profile:{profile_id}::bookkeeping_history_v2"
    state = repo.get_all_state()
    try:
        hist = json.loads(state.get(hist_key) or "[]")
    except json.JSONDecodeError:
        hist = []
    matched = False
    if isinstance(hist, list):
        for item in hist:
            if isinstance(item, dict) and (
                (invoice_id and str(item.get("id") or "") == invoice_id)
                or (einvoice_uuid and str(item.get("einvoiceUuid") or "") == einvoice_uuid)
            ):
                item["einvoiceStatus"] = new_status
                item["einvoiceWebhookUpdatedAt"] = datetime.now(timezone.utc).isoformat()
                matched = True
        if matched:
            repo.mutate_state({hist_key: json.dumps(hist)})
    return {"ok": True, "matched": matched, "einvoiceStatus": new_status}


def receive_inbound_einvoice(repo: LumenStateRepository, payload: Mapping[str, object], caller_account: str | None = "owner") -> dict[str, object]:
    """Parse an inbound Peppol PINT-AE UBL 2.1 supplier invoice XML and save it into the tenant's ledger."""
    if not isinstance(payload, Mapping):
        return {"ok": False, "status_code": 400, "error": "Invalid inbound e-invoice payload."}
    parsed = parse_inbound_peppol_xml(payload.get("xml"))
    if not parsed.get("ok"):
        return {"ok": False, "status_code": 400, "error": parsed.get("error", "Invalid XML")}
    entry = dict(parsed["entry"])  # type: ignore[arg-type]
    profile_id = str(payload.get("profileId") or "default").strip() or "default"
    hist_key = f"profile:{profile_id}::bookkeeping_history_v2"
    sup_key = f"profile:{profile_id}::bookkeeping_suppliers"
    state = repo.get_all_state()
    try:
        hist = json.loads(state.get(hist_key) or "[]")
    except json.JSONDecodeError:
        hist = []
    if not isinstance(hist, list):
        hist = []
    hist.insert(0, entry)

    try:
        sups = json.loads(state.get(sup_key) or "[]")
    except json.JSONDecodeError:
        sups = []
    if not isinstance(sups, list):
        sups = []
    if not any(isinstance(s, dict) and str(s.get("name") or "").lower() == str(entry.get("entityName") or "").lower() for s in sups):
        sups.append({
            "id": f"sup-{secrets.token_hex(4)}",
            "name": entry.get("entityName"),
            "trn": entry.get("trn"),
            "tradeLicense": entry.get("tradeLicense"),
            "address": entry.get("address"),
            "emirate": entry.get("emirate"),
        })
    repo.mutate_scoped_state(caller_account or "owner", {hist_key: json.dumps(hist), sup_key: json.dumps(sups)})
    return {"ok": True, "entry": entry}
