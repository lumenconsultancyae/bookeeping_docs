# Software Design Document (SDD): Target Architecture Delta & Gap Roadmap

## 1. Current Baseline vs. Target Architecture Delta

| Architectural Dimension | Current Baseline (`bookkeeping-tool` + `bookeeping_docs` Stack) | Target Architecture Delta |
| :--- | :--- | :--- |
| **Application Structure** | Monolithic SPA (`index.html` + `script.js` + `style.css`) served by `nginx:alpine` (`bookkeeping-web`) with `sub_filter` runtime patches and `/__vendor__/` shims in `default.conf`. | Modular ES module architecture (`src/domain/`, `src/services/`, `src/ui/`) bundled with Vite and strict compile-time TypeScript schema validation. |
| **State & Persistence** | Browser `localStorage` keys (`bookkeeping_history_v2`, `bookkeeping_coa`, etc.) scoped to a single browser profile. | Transactional REST/GraphQL backend backed by PostgreSQL with multi-tenant row-level security and server-side audit logging. |
| **AI Document Pipeline & Security** | Client-side raw PDF/image Base64 upload posted with `X-Lumen-Client: lumen-bookkeeping-web` via Cloudflare Pages Function (`functions/api/[[path]].js`) / Nginx `/api/v1/prediction/*` to `agy_service.py` (protected by `Origin` allowlisting, `X-Lumen-Client` verification, and constant-time `X-Agy-Proxy-Secret` HMAC verification), which saves uploads to an isolated request directory and invokes `agy --mode accept-edits --dangerously-skip-permissions --disable-slash-commands --output-format json --print`. | Asynchronous multi-page document ingestion queue with per-page VLM extraction, per-user JWT/OAuth2 bearer authentication, persistent object storage, and native `--json-schema` enforcement. |
| **Ledger Synthesis** | Read-time synthesis of Fixed Asset (`DEPR`/`AMRT`) and Accrual (`ACCR`) journal entries inside `getHistory()`. | Scheduled idempotent ledger posting worker persisting immutable journal headers and line items with audit timestamps. |

---

## 2. Unresolved Gaps & Proposed Solution / Next Steps Roadmap

A comprehensive code audit of `index.html` and `script.js` in `bookkeeping-tool` identified the following architectural compromises and edge-case defects in the upstream source code, along with active runtime mitigations in `default.conf` and concrete remediation paths:

### Gap 1: Undeclared `isVatApplicable` Reference in `buildCustomerEntry()`
- **Current Behavior**: In `script.js` (line 4273), `buildCustomerEntry()` computes `const vat = isVatApplicable ? (sub * 0.05) : 0;`, whereas the VAT radio toggle (`input[name="vatToggle"]`) updates `vatTreatment` (`'standard' | 'zero' | 'exempt'`), as used in `window.calcCustTotals()` (line 4129). In the deployed stack, Nginx `default.conf` applies a `sub_filter` rewrite (`typeof isVatApplicable !== "undefined" ? isVatApplicable : (vatTreatment === "standard")`) so customer invoice creation works without modifying `bookkeeping-tool`.
- **Proposed Solution / Next Steps**:
  1. Replace `const vat = isVatApplicable ? (sub * 0.05) : 0;` directly in `bookkeeping-tool/script.js` line 4273 with `const vat = vatTreatment === 'standard' ? (sub * 0.05) : 0;`.
  2. Persist `vatTreatment` on the saved customer invoice object so downstream FTA VAT201 reporting can distinguish Zero-Rated (Box 6) from Exempt (Box 7) supplies.

### Gap 2: Unmapped `view-expense` Navigation Item in Sidebar
- **Current Behavior**: `index.html` (line 45) includes `<a href="#" class="nav-item" data-target="view-expense">Expenses</a>`, but no `<div id="view-expense" class="app-view">` container exists in the DOM. Clicking `Expenses` causes `document.getElementById(targetId).style.display = 'block'` in `switchView()` (line 148) to throw a null-reference `TypeError`.
- **Proposed Solution / Next Steps**:
  1. Add a null-guard in `switchView()`: `const targetEl = document.getElementById(targetId); if (!targetEl) return;`.
  2. Either route `Expenses` to `view-supplier` / `view-journal` (Petty Cash) or introduce a dedicated `#view-expense` view container.

### Gap 3: Nested `view-audit` Condition Inside `view-assets` Branch in `switchView()`
- **Current Behavior**: In `script.js` (lines 201–204), `if (targetId === 'view-audit') renderAuditLog();` is nested inside `if (targetId === 'view-assets') { ... }`. As a result, navigating directly to `view-audit` does not invoke `renderAuditLog()` unless an audit event was logged while `#view-audit` was already displayed.
- **Proposed Solution / Next Steps**:
  1. Move `if (targetId === 'view-audit') renderAuditLog();` out of the `if (targetId === 'view-assets')` block in `switchView()` so `#auditLogBody` renders immediately whenever the user navigates to **Audit Log**.

### Gap 4: Property Name Mismatch & Initial Stock Double-Counting in Inventory / Quote / PO Workflows
- **Current Behavior**:
  - `saveInventoryItem()` in `script.js` initializes `if (isNew) itemPayload.qty = initialQty;` and then invokes `window.logStockMovement(..., initialQty, ...)`, which increments `qty` a second time (`2 * initialQty`). In the deployed stack, Nginx `default.conf` rewrites `if (isNew) itemPayload.qty = initialQty;` to `if (isNew) itemPayload.qty = 0;` via `sub_filter`.
  - `saveInventoryItem()` stores `{ name, sku, desc, cost, markup, price, qty }`, whereas `renderQuoteLineItem()` reads `item.sellingPrice` and `renderPOLineItem()` reads `item.costPrice`.
  - `convertQuoteToInvoice()` and `convertPOToBill()` push records with `type: 'customer_invoice'` / `type: 'supplier_invoice'` and `amount`, whereas `getHistory()` consumers expect `type: 'customer'` / `type: 'supplier'`, `status: 'posted'`, `subtotal`, `tax`, and `total`.
- **Proposed Solution / Next Steps**:
  1. Commit `if (isNew) itemPayload.qty = 0;` directly in `bookkeeping-tool/script.js` so `logStockMovement()` is the single source of truth for inventory quantity updates.
  2. Normalize inventory property lookups in `renderQuoteLineItem()` to `item.price ?? item.sellingPrice` and in `renderPOLineItem()` to `item.cost ?? item.costPrice`.
  3. Normalize `convertQuoteToInvoice()` and `convertPOToBill()` to emit standard ledger schemas (`type: 'customer' | 'supplier'`, `status: 'posted'`, `invoiceNum`, `subtotal`, `tax: '0.00'`, `total`).

### Gap 5: Client-Side `localStorage` Capacity & Multi-User Concurrency Limits
- **Current Behavior**: Storing Base64-encoded document images (`fileBase64`) alongside ledger records in `localStorage` is constrained by the browser's 5–10 MB origin quota and lacks multi-user synchronization.
- **Proposed Solution / Next Steps**:
  1. Offload binary document attachments (`fileBase64`) to object storage (S3/MinIO) or IndexedDB in local-only mode, storing only content-addressed object URIs in the ledger record.
  2. Migrate `localStorage` CRUD helpers (`getRawHistory`, `saveToHistory`, `updateHistory`) to an async repository interface backed by PostgreSQL.
