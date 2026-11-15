"""Backend document & invoice upload validation for `agy_service.py`."""

from __future__ import annotations

import json
from pathlib import Path
import re

_VALIDITY_RULE = (
    "- DOCUMENT VALIDITY GATE: First verify whether the document is genuinely a valid invoice, bill, receipt, or financial statement matching the request.\n"
    "- If the document is NOT a valid invoice/bill/receipt/statement (e.g., photos of dogs or animals, people, scenery, blank pages, memes, brochures, textbooks, or unrelated non-financial content), DO NOT invent or guess fields. Respond ONLY with:\n"
    '  ```json\n  {"isValidInvoice": false, "documentType": "non_invoice", "rejectionReason": "Concise explanation of why the document is not a valid invoice"}\n  ```\n'
)


def build_extraction_prompt(question: str, saved_files: list[Path]) -> str:
    """Build the full `agy` extraction prompt with strict document-validity rules."""
    if saved_files:
        files_list = "\n".join(f"- {p}" for p in saved_files)
        return (
            "You are an accounting document extraction engine.\n"
            f"First, call the `read_file` tool ONCE on each uploaded document file below:\n{files_list}\n\n"
            "CRITICAL RULES:\n"
            "- Use ONLY the `read_file` tool. Do NOT call `run_command`, `write_file`, `edit_file`, or any other tool.\n"
            f"{_VALIDITY_RULE}"
            "- Extract all values directly from the document content returned by `read_file`.\n"
            "- Ensure every line item `amount` and `unitPrice` is the pre-tax net amount (excluding VAT/tax), and `subtotal` is the sum of pre-tax line item amounts so that `subtotal - discount + tax = total`.\n"
            f"- Respond ONLY with the requested ```json ... ``` code block (no extra prose):\n\n{question}"
        )
    if "json" in question.lower() or "extract" in question.lower() or "bank statement" in question.lower():
        return (
            "You are an accounting document extraction engine.\n"
            "CRITICAL RULES:\n- Do NOT call `read_file`, `list_dir`, `find_by_name`, `run_command`, `write_file`, `edit_file`, or any other tool.\n"
            f"{_VALIDITY_RULE}"
            f"- Fulfill the extraction instructions below and respond ONLY with the requested ```json ... ``` code block (no extra prose):\n\n{question}"
        )
    return (
        "CRITICAL RULES:\n- Do NOT call `run_command`, `write_file`, `edit_file`, or any other tool.\n"
        f"- Respond directly and helpfully to the user prompt below:\n\n{question}"
    )

_INVALID_DOC_TYPES = frozenset(
    {
        "non_invoice",
        "non-invoice",
        "unrelated",
        "photo",
        "image",
        "animal",
        "dog",
        "dogs",
        "blank",
        "invalid",
        "other",
        "meme",
        "article",
        "book",
    }
)

_PLACEHOLDER_STRINGS = frozenset(
    {
        "",
        "-",
        "--",
        "n/a",
        "na",
        "none",
        "null",
        "undefined",
        "unknown",
        "sample",
        "test",
        "invoice date",
        "exact invoice number",
        "supplier name",
        "customer name",
        "merchant or payee name",
        "trn number",
        "supplier address",
        "supplier phone",
        "customer address",
        "customer phone",
        "receipt or invoice number",
        "short description of items/expense",
        "code and name",
        "currency code",
        "yyyy-mm-dd",
        "item",
        "bank name",
        "account number",
        "transaction details",
        "supplier / item description",
        "receipt date",
        "receipt number",
    }
)

_IDENTITY_KEYS = ("entityName", "supplierName", "customerName", "vendor", "invoiceNum", "reference", "description")


def validate_uploaded_file_bytes(file_bytes: bytes, safe_name: str, mime: str, error_cls: type[Exception]) -> None:
    """Validate uploaded PDF or image magic bytes and reject empty, disguised, or corrupted files."""
    if not file_bytes:
        raise error_cls("Uploaded document is empty.")
    name_lower = safe_name.lower()
    mime_lower = (mime or "").lower()
    is_pdf = "pdf" in mime_lower or name_lower.endswith(".pdf")
    if is_pdf:
        if b"%PDF-" not in file_bytes[:1024]:
            raise error_cls("Invalid PDF file: the uploaded document is not a valid PDF.")
        return
    is_image = mime_lower.startswith("image/") or name_lower.endswith(
        (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".heic", ".heif")
    )
    if is_image:
        valid_img = (
            file_bytes.startswith(b"\x89PNG\r\n\x1a\n")
            or file_bytes.startswith(b"\xff\xd8\xff")
            or file_bytes[:6] in (b"GIF87a", b"GIF89a")
            or (file_bytes[:4] == b"RIFF" and file_bytes[8:12] == b"WEBP")
            or file_bytes.startswith(b"BM")
            or file_bytes[4:8] == b"ftyp"
        )
        if not valid_img:
            raise error_cls("Invalid image file: the uploaded document is corrupted or not a supported image.")


def extract_json_block(text: str) -> object | None:
    """Extract the first fenced or raw JSON object/array from an AI prediction response."""
    raw = (text or "").strip()
    if not raw:
        return None
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw, flags=re.IGNORECASE)
    candidate = fenced.group(1).strip() if fenced else raw
    for opener, _closer in (("{", "}"), ("[", "]")):
        if candidate.startswith(opener):
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass
    obj_start, arr_start = raw.find("{"), raw.find("[")
    if arr_start != -1 and (obj_start == -1 or arr_start < obj_start):
        arr_end = raw.rfind("]")
        if arr_end > arr_start:
            try:
                return json.loads(raw[arr_start : arr_end + 1])
            except json.JSONDecodeError:
                pass
    if obj_start != -1:
        obj_end = raw.rfind("}")
        if obj_end > obj_start:
            try:
                return json.loads(raw[obj_start : obj_end + 1])
            except json.JSONDecodeError:
                pass
    return None


def parse_money(val: object) -> float:
    """Parse a numeric or formatted money string into a float."""
    if val is None or isinstance(val, bool):
        return 0.0
    if isinstance(val, (int, float)):
        return float(val) if val == val else 0.0
    cleaned = re.sub(r"[^\d.-]", "", str(val).replace(",", ""))
    try:
        return float(cleaned) if cleaned else 0.0
    except ValueError:
        return 0.0


def clean_text_field(val: object) -> str:
    """Return a stripped text value, or empty string if it matches a known placeholder."""
    if val is None:
        return ""
    s = str(val).strip()
    return "" if s.lower() in _PLACEHOLDER_STRINGS else s


def validate_ai_document_response(
    question: str,
    response_text: str,
    *,
    has_uploads: bool,
    error_cls: type[Exception],
) -> None:
    """Validate structured AI extraction output for invoices, receipts, and bank statements."""
    q_low = (question or "").lower()
    is_bank_prompt = "bank statement" in q_low
    is_invoice_prompt = any(
        k in q_low
        for k in (
            "supplier invoice",
            "customer invoice",
            "expense receipt",
            "petty cash receipts",
            "invoice",
            "receipt",
            "document text:",
            "extracted document text:",
        )
    )
    if not has_uploads and not is_invoice_prompt and not is_bank_prompt:
        return
    parsed = extract_json_block(response_text)
    if parsed is None:
        raise error_cls("The uploaded document does not appear to be a valid invoice, bill, or receipt.")
    items_to_check = parsed if isinstance(parsed, list) else ([parsed] if isinstance(parsed, dict) else [])
    if not items_to_check:
        raise error_cls("No valid receipts or invoices were found in the uploaded document.")
    for entry in items_to_check:
        if not isinstance(entry, dict):
            raise error_cls("The uploaded document is not a valid invoice, bill, or receipt.")
        if (
            entry.get("isValidInvoice") is False
            or entry.get("isValidDocument") is False
            or entry.get("isValidStatement") is False
            or entry.get("isValidBankStatement") is False
            or entry.get("valid") is False
            or str(entry.get("documentType") or "").strip().lower() in _INVALID_DOC_TYPES
        ):
            reason = clean_text_field(entry.get("rejectionReason") or entry.get("reason") or entry.get("error"))
            raise error_cls(reason or "The uploaded document is not a valid invoice, bill, or receipt.")
    if is_bank_prompt:
        has_valid_statement = False
        for entry in items_to_check:
            if not isinstance(entry, dict):
                continue
            bank_name = clean_text_field(entry.get("bankName"))
            acc_num = clean_text_field(entry.get("accountNumber"))
            raw_txns = entry.get("transactions") if isinstance(entry.get("transactions"), list) else []
            valid_txns = [
                tx
                for tx in raw_txns
                if isinstance(tx, dict)
                and clean_text_field(tx.get("description") or tx.get("transaction"))
                and parse_money(tx.get("amount")) != 0
            ]
            bal = parse_money(entry.get("closingBalance") if "closingBalance" in entry else entry.get("statementBalance"))
            if valid_txns or (bank_name and acc_num and bal != 0):
                has_valid_statement = True
                break
        if not has_valid_statement:
            raise error_cls("No valid bank statement details or transactions were found in the uploaded document.")
        return

    has_any_valid_invoice = False
    for entry in items_to_check:
        if not isinstance(entry, dict):
            continue
        total_val = parse_money(entry.get("total"))
        subtotal_val = parse_money(entry.get("subtotal"))
        raw_items = entry.get("items") if isinstance(entry.get("items"), list) else []
        valid_items = [
            it
            for it in raw_items
            if isinstance(it, dict)
            and clean_text_field(it.get("description") or it.get("name") or it.get("item"))
            and (parse_money(it.get("amount")) > 0 or parse_money(it.get("unitPrice")) > 0)
        ]
        present_id_keys = [k for k in _IDENTITY_KEYS if k in entry and entry.get(k) not in (None, "")]
        non_placeholder_ids = [k for k in present_id_keys if clean_text_field(entry.get(k))]
        if present_id_keys and not non_placeholder_ids and not valid_items:
            continue
        if total_val > 0 or subtotal_val > 0 or valid_items:
            has_any_valid_invoice = True
            break
    if not has_any_valid_invoice:
        raise error_cls("No valid invoice amounts or line items were found in the uploaded document.")
