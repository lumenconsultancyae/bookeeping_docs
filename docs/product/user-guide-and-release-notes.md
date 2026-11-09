# Lumen Accounting Suite User Guide

## Product Overview

Lumen Accounting Suite (Lumen Books) is an all-in-one financial management, bookkeeping, and compliance platform tailored for small and mid-sized businesses operating in the United Arab Emirates. It streamlines daily accounting operations by combining a double-entry general ledger, AI-powered document capture, inventory and fixed-asset tracking, UAE Wage Protection System (WPS) payroll, and automated UAE Value Added Tax (VAT) and Corporate Tax reporting.

---

## Executive Dashboard

When you open Lumen Accounting Suite, the **Dashboard** provides an immediate overview of your business health:

- **Period Selector**: Filter Profit & Loss metrics by a specific **Year** and **Month**, or select **All Time** / **Whole Year** for cumulative analysis.
- **Executive Hero KPIs**:
  - **Cash Runway**: Estimated months of operation remaining based on current cash reserves and your 90-day average burn rate.
  - **Avg. Monthly Burn**: Average monthly operating expenses over the trailing 90 days.
  - **Net Profit Margin**: Net profit expressed as a percentage of total revenue.
  - **Current Cash**: Current reconciled cash and bank balance.
- **Cash Flow Visualization & Action Lists**:
  - A 6-month **Cash In vs. Cash Out** bar chart highlights monthly liquidity trends.
  - **Critical Receivables (Owe You)** and **Critical Payables (You Owe)** list overdue invoices exceeding 30 days so collections and vendor payments can be prioritized.
- **Detailed Accounting KPIs**: Clickable cards for **Total A/R**, **Total A/P**, **Total Revenue**, **Total Expenses** (with an interactive **Breakdown** modal), **VAT Summary**, **Corp. Tax Liab.**, and **Net Profit / (Loss)** jump directly to the filtered General Ledger view.
- **Live 9% UAE Corporate Tax & Small Business Relief Tracker**:
  - Tracks your real-time **Adjusted Taxable Income** against the UAE **AED 375,000 (0% Bracket)** threshold and estimates **9% Corporate Tax** on income above the threshold.
  - Monitors gross revenue against the **AED 3,000,000 Small Business Relief (Article 21)** cap, displaying remaining revenue headroom, effective tax rate, non-deductible add-backs, and Qualifying Free Zone (0% QFZP) status.
- **UAE Compliance & Renewal Reminders**:
  - Tracks company **Trade License** and **Establishment Card** expiry dates (configured in **Settings**) alongside employee **Residence Visa** and **Emirates ID** expiry dates, flagging items as **Expired**, **Due within 30 days (Urgent)**, **Due within 60 days (Warning)**, or **Valid**.
- **Upcoming PDC Cheques Reminder (`#pdcReminderCard`)**:
  - Displays pending post-dated cheques from the **Cheque Registry** that are scheduled to clear within the next **30 days**, showing the **Supplier Name**, **Clearing Date**, **AED Amount**, and urgency badge (**Today**, **In Xd**, or **Overdue**).

---

## Managing Contacts, Inventory & Fixed Assets

### Customers & Suppliers
Navigate to **CONTACTS > Customers** or **CONTACTS > Suppliers** to maintain your business directory:
- Record entity names, physical addresses, email addresses, phone numbers, 15-digit UAE VAT Tax Registration Numbers (**TRN**), and default payment terms.
- Edit existing contact profiles inline by clicking **Edit** in the directory table.
- Customers with linked sales invoices are protected from accidental deletion to preserve ledger integrity.

### Inventory Directory & Stock Ledger
Navigate to **INVENTORY > Inventory Directory** to manage physical products:
- Enter the **Product Name**, **SKU / Code**, **Description**, **Unit Cost (AED)**, **Markup (%)**, **Selling Price (AED)**, and **Initial Quantity**.
- Entering a **Unit Cost** and **Markup (%)** automatically calculates the **Selling Price**, and adjusting the **Selling Price** automatically recalculates the **Markup (%)**.
- View all historical stock additions (`IN`) and deductions (`OUT`) under **INVENTORY > Stock Ledger**.

### Fixed Assets, Accruals & Deferred Revenue
- **Fixed Assets (`ASSETS > Assets Directory`)**: Track capital equipment and property with purchase dates, locations, initial values, and useful life in years. The suite automatically generates monthly straight-line depreciation entries and computes accumulated depreciation and net book value.
- **Accruals, Prepayments & Deferred Revenue (`ACCOUNTING > Accruals`)**: Register prepaid expenses (such as annual office rent or software subscriptions) or unearned customer advances (`2150 Deferred Revenue`) with either a straight-line monthly schedule or a **Usage / Milestone Recognition** schedule. For usage-based contracts, click **Record Usage** to recognize revenue proportionally as units or milestones are delivered.

---

## Commercial Transactions & AI Document Capture

### Quotes & Purchase Orders
- **Quotes & Estimates (`TRANSACTIONS > Quotes & Estimates`)**: Create pre-sales quotes for clients using preset consulting/accounting services, custom descriptions, or inventory items. Preview or print formatted client quotes, and click **Convert to Invoice** once approved to generate a sales invoice in the ledger.
- **Purchase Orders (`TRANSACTIONS > Purchase Orders`)**: Issue purchase orders to suppliers, inspect printable PO documents via **View / Print**, mark partial or full deliveries via **Receive Goods**, and complete procurement using **3-Way Match & Bill** to convert received quantities directly into supplier bills.

### Sales Invoices, Tax Credit Notes & UAE PINT-AE E-Invoicing
Navigate to **TRANSACTIONS > Sales Invoices** to bill customers and manage credit adjustments:
- **AI Auto-Fill (Optional)**: Upload an existing PDF or image invoice to automatically populate customer details, line items, and tax treatment.
- **Manual Generation**: Select or enter a customer name, Emirate place of supply, payment terms, revenue account (`Service Revenue`, `Product Sales`, `Consulting Income`, `Other Revenue`, or `Deferred Revenue`), line items, and tax treatment (**Standard 5%**, **Zero-Rated 0%**, or **Exempt**).
- **Inventory & COGS Automation**: Selling an inventory item under `Product Sales` automatically deducts stock in the **Stock Ledger** and posts a corresponding **Cost of Goods Sold (COGS)** entry.
- **UAE PINT-AE XML E-Invoicing, Executive A4 Print Layout & 1-Tap WhatsApp Sharing**:
  - Select **English Only (EN)** or **Arabic Only (AR)** for your invoice document and WhatsApp message, and optionally attach a **Payment Link** (such as Ziina, Stripe, or PayTabs).
  - Click **Preview E-Invoice** to inspect or print an isolated A4 executive **Tax Invoice** featuring a top-left logo, top-right company details, centered **TAX INVOICE** / **فاتورة ضريبية** banner, left **Billed To** card, right 4-field metadata card (**Invoice No.**, **Invoice Date**, **Terms**, **Due Date**), fixed-width item table, **Dirhams Only.** amount in words, and a computer-generated document footer note, or export a validated **UAE Peppol PINT-AE UBL 2.1 XML** document (Invoice `380` or Tax Credit Note `381`).
  - Click **Share via WhatsApp** to normalize UAE mobile numbers (`050...` to `97150...`) and launch a 1-tap WhatsApp message containing the formatted invoice summary and payment link.
- **Tax Credit Notes (FTA Article 60)**: Issue a linked **Tax Credit Note (`CRN-####`)** against any posted sales invoice to record returns, discounts, or billing adjustments, automatically reversing Output VAT, revenue, and open customer receivables.

### Supplier Bills & Direct Expenses
- **Supplier Bills (`TRANSACTIONS > Supplier Bills`)**: Drag and drop a PDF, PNG, or JPG vendor invoice and click **Analyze Document**. Review extracted line items, foreign currency conversion to AED, and suggested accounts, optionally flag items as **Corporate Tax Add-Back**, and click **Confirm & Save to Ledger**.
- **Direct Expenses & Camera Receipt TRN OCR (`TRANSACTIONS > Expenses`)**: Record immediate out-of-pocket or card/bank expenses paid directly from **Cash**, **Bank**, **Petty Cash**, or **Accounts Payable**, or click **Snap Camera Receipt** to extract and validate the vendor's **15-digit UAE Tax Registration Number (TRN)**, Emirate place of supply, net amount, and **5% VAT** automatically.

### Banking, Reconciliation & Cheque Registry
- **Banking (`TRANSACTIONS > Banking`)**:
  - View statement vs. ledger balances and unreconciled differences across all bank accounts.
  - Configure automated categorization rules in the **Bank Rules Engine** (matching transaction descriptions to specific accounts and VAT rates).
  - Upload PDF or image bank statements for AI transaction extraction, match payments directly against open customer or supplier invoices, and save reconciled statements.
- **Cheque Registry (`TRANSACTIONS > Cheque Registry`)**: Register and track issued cheques by cheque number, issue date, maturity date, supplier, and source bank account.
- **Recurring Transactions (`AUTOMATION > Recurring Transactions`)**: Set up weekly, monthly, or yearly templates for recurring invoices, bills, or journal entries that post automatically on their scheduled run date.

---

## Accounting, Payroll & Financial Reporting

### Chart of Accounts, Journal Entries & General Ledger
- **Chart of Accounts (`ACCOUNTING > Chart of Accounts`)**: Add, edit, or remove Asset, Liability, Equity, Revenue, and Expense accounts.
- **Journal Entries (`ACCOUNTING > Journal Entries`)**: Post manual double-entry journals with live **Preview Posting**, or batch-upload multiple petty cash receipts for AI extraction.
- **General Ledger (`ACCOUNTING > General Ledger`)**: Filter all transactions by date range, type, entity, account, or status; match payments to open invoices; and lock completed accounting periods using **Close Month For Editing** (`Lock Ledger`).
- **Statement of Account (`ACCOUNTING > SOA`)**: View running balances and KPI summaries (**Total Invoice Value**, **Total Payments**, and **Balance**) for any individual customer/supplier, or across **All Accounts Payable** and **All Accounts Receivable**.

### Payroll, Timesheets, MOHRE UAE WPS & Statutory Gratuity (EOSB)
Navigate to **PAYROLL > Employee details**, **PAYROLL > Timesheet & WPS**, and **Settings > Company Letterhead Settings**:
- Configure **Company Contact Number** (`#companyPhone`), Company Name, Address, TRN, and Company Logo in **Settings** so they appear on your letterhead across E-Invoices and employee Payslips.
- Maintain employee records including Employee ID, 14-digit MOHRE Labour Card Number, IBAN, 9-digit Bank Routing Code, Residence Visa Expiry, Emirates ID Expiry, Basic Salary, Housing, Telephone, and Other Allowances.
- Use the **Employee** (`#filterTimesheetEmployee`) and **Month** (`#filterTimesheetMonth`) filters on **Timesheet & WPS** to filter payroll records by employee or pay period; the employee filter automatically lists all active employees from the Employee Directory even before any timesheets are saved.
- Open the monthly **Timesheet (UAE WPS)** modal to record days worked, bonuses, loan deductions, and other deductions, and optionally accrue **End of Service Benefits (EOSB)** and leave salary (`6520 EOSB & Leave Expense`).
- Use the **UAE Article 51 Statutory Gratuity Calculator** to simulate or accrue End-of-Service Gratuity under UAE Federal Decree-Law No. 33 of 2021 (**21 days/year** basic salary for the first 5 years, **30 days/year** for service beyond 5 years, automatic exclusion of unpaid leave days, and the **2-year total wage cap**).
- Click **Save Payroll** to post all payroll journal entries (`6500 Payroll / Salaries`, `6520 EOSB & Leave Expense`, `2100 Accrued Liabilities`, `2120 Provision for EOSB`, and Bank/Cash disbursement) directly to the General Ledger, Profit & Loss, Balance Sheet, Trial Balance, Cash Flow, and Dashboard KPIs; click **Payslip** on any employee row to preview and print a **Professional Payslip Document** displaying company branding, contact number, employee designation, starting date, itemized earnings and deductions, and net salary in words; and click **Download WPS (.sif)** to export a compliant UAE Wage Protection System Salary Information File.

### Tax Compliance, FP&A & Financial Statements
- **UAE VAT 201, FTA Audit File (FAF) & Corporate Tax (`TAX > VAT` & `Corporate Tax`)**:
  - Generate Emirate-level **FTA VAT 201** return summaries (Boxes `1a` through `1g` across Abu Dhabi, Dubai, Sharjah, Ajman, Umm Al Quwain, Ras Al Khaimah, and Fujairah, plus Boxes 2 through 14) showing standard-rated supplies, Tax Credit Note reductions, Reverse Charge, Zero-Rated and Exempt supplies, recoverable input tax, and net payable/refundable VAT.
  - Click **Download FTA Audit File (FAF .csv)** to export a 5-section UAE Federal Tax Authority Audit File (`CompInfo`, `Customer`, `PurcData`, `SuppData`, `GLData`) for tax audit readiness.
  - Review **UAE Corporate Tax** calculations showing Net Profit, non-deductible Add-Backs across all expense categories, Adjusted Taxable Income, and estimated 9% Corporate Tax above the AED 375,000 threshold (respecting Mainland vs. Qualifying Free Zone and Small Business Relief settings).
- **FP&A (`FP&A > Budgeting vs. Actuals` & `Cash Flow Forecast`)**:
  - Set monthly account budgets and monitor real-time variances (`Target Met`, `Under Target`, `Under Budget`, `Over Budget`).
  - View a 90-day **Cash Flow Forecast** projecting your running cash balance from open receivables and payables by due date.
- **Financial Reports (`REPORTS`), Multi-Company Profiles & Audit Log**:
  - Generate real-time **Profit & Loss**, **Balance Sheet**, **Cash Flow**, **Statement of Equity**, and **Trial Balance** statements.
  - Switch between multiple company profiles, toggle the interface between **English (`EN`)** and **Arabic (`عربي`)** with Right-to-Left (RTL) layout, manage your subscription plan (**Basic** AED 50/mo, **Advance** AED 75/mo, **Premium** AED 100/mo — **1 Month Free** promotional offer & **Corporate Tax Only (0% VAT)**) secured by salted **PBKDF2-SHA256 (120,000 iterations)** password hashing, and inspect the **Audit Log** for a chronological compliance record of system creations, updates, and deletions.

---

## Release Notes

### Latest Release Highlights

- **Upcoming PDC Cheques Dashboard Reminder, Collapsed Sidebar SVG Icons, 1-Month Free Trial Billing, 3x Lockout & Playwright E2E Suite**: Added the **Upcoming PDC Cheques** reminder card (`#pdcReminderCard`) on the Executive Dashboard displaying supplier name, clearing date, and AED amount for pending post-dated cheques clearing within 30 days; added semantic SVG icons across all 31 sidebar submenu items when collapsed (`body.sidebar-collapsed`); added **1-Month Free Trial** credit card capture (`#setupCardName`, `#setupCardNumber`, `#setupCardExpiry`, `#setupCardCvv`) with PCI-safe tokenization, pre-renewal email reminders (`/api/v1/auth/trial-reminder`), cancel/resume auto-renewal in Settings (`#btnToggleAutoRenew`), automatic renewal deduction (`/api/v1/auth/trial-renew`), SVG eye/eye-off password visibility toggles, **Remember me** checkbox, **3-attempt password lockout**, and **6-digit email password reset** (`/api/v1/auth/password-reset/request`, `/api/v1/auth/password-reset/confirm`); hardened online-only cloud state by disabling browser IndexedDB attachment caching in HTTP/HTTPS mode and enforcing `Cache-Control: no-store`; and migrated the BDD E2E and DOM test harnesses from Selenium to **Playwright**.
- **React 18 SPA Architecture, Declarative Shell, Tenant-Scoped Query Store & React DevTools Support**: Migrated `index.html` from 50 separate global `<script>` tags to a clean `<div id="root"></div>` React 18 SPA shell powered by `react-runtime.js` (`window.React`, `window.ReactDOM`, hooks, `React.html`, `createRoot`, `mountDeclarativeRoot`, and full `__REACT_DEVTOOLS_GLOBAL_HOOK__` Fiber tree inspection across `/`, `/welcome`, and `/admin`), `react-store.js` (tenant-scoped `LumenQueryKeys`, `LumenQueryCache` with optimistic rollback and non-4xx bounded retries, and `LumenReactStore` / `useLumenStore` with bidirectional `#view-*` hash and `?year=&month=` query parameter synchronization), `views-dashboard.js` (`<LumenApp />`, `<SidebarNav />`, `<Topbar />`, `<DashboardView />`, `<NotFoundView />`), and `react-app.js` (`LUMEN_MODULE_MANIFEST`).
- **Server-Backed Cross-Computer Multi-Tenant Sync, Cloudflare D1/R2 & Strict `localStorage` UI Config Isolation**: Added thread-safe SQLite (`LumenStateRepository`) and Cloudflare D1 (`LUMEN_DB`) + R2 (`LUMEN_ATTACHMENTS`) server/edge persistence (`/api/v1/state`, `/api/v1/attachments`, `/api/v1/auth/login`, and `/api/v1/auth/session`) with 120,000-iteration PBKDF2-HMAC-SHA256 authentication and Cloudflare Zero Trust Access support so customer accounts, company profiles, ledger transactions, expenses, and PDF/image invoice attachments uploaded on one computer are immediately visible when an administrator signs in to `/admin` or opens Advisor Mode (`Open Books`) on another computer; and isolated physical browser `localStorage` strictly to user UI preferences (`lumen_lang`, `lumen_sidebar_collapsed`, `lumen_table_page_size:*`) while moving per-tab session state to `sessionStorage`.
- **Professional Branded Payslips, Active-Employee Timesheet Filtering, Payroll P&L Posting & Welcome 1-Month Free Pricing**: Redesigned employee payslips (`renderPayslipDocument` / `generatePayslip`) with full company letterhead branding (logo, address, `#companyPhone` contact number, TRN, MOHRE ID), employee designation and starting date, itemized earnings/deductions tables, and net salary in words; updated `#filterTimesheetEmployee` (`populateTimesheetEmployeeFilter`) to list all active employees even before timesheets are saved and filter saved payroll runs by employee and period; ensured `savePayroll()` and `ar-posting-fix.js` post and backfill `6500 Payroll / Salaries` and `6520 EOSB & Leave Expense` journals across P&L, Balance Sheet, Trial Balance, Cash Flow, and KPIs; and updated subscription pricing to **Basic AED 50/mo**, **Advance AED 75/mo**, and **Premium AED 100/mo** with a **1 Month Free** promotional offer across all tiers.

- **Professional Interaction Patterns, Paginated Lists & Mobile Drawer**: Replaced every blocking browser pop-up with in-app notifications (green for saves, blue for deletions/cancellations, red for errors) and styled confirmation dialogs that name the record before anything is deleted; long lists such as the General Ledger, Customers, Suppliers and Chart of Accounts now page inside their card with *rows per page*, page numbers and search, and jump to and highlight the record you just saved; forms show specific errors under the field (for example *"TRN must be exactly 15 digits"*) instead of browser tooltips; and on tablets and phones the menu opens as a slide-in drawer with full-width confirmation sheets.
- **Enterprise Finance Navy & Royal Sapphire UI/UX Overhaul**: Unified the color palette across Onboarding, Main Books Workspace, and Super-Admin Console to Enterprise Finance Navy (`#0c1a2e`) and Royal Sapphire (`#1d4ed8`); added semantic SVG icons and tooltips across all 31 submenu items when the sidebar is collapsed; expanded the 6-month Cash Flow chart across the full card width with gridlines and legend; aligned multi-column form rows, line-item editors, financial summary boxes, and tabular numeric columns; and replaced all platform-dependent emoji glyphs with crisp vector icons.
- **Live UAE 9% Corporate Tax & Small Business Relief Tracker**: Added a real-time Home Dashboard tracker monitoring Adjusted Taxable Income against the AED 375,000 (0% bracket) threshold, 9% Corporate Tax liability, Article 21 AED 3,000,000 Small Business Relief eligibility and headroom, and Qualifying Free Zone Person (0% QFZP) status.
- **UAE Compliance Expiry Reminders & MOHRE WPS / Article 51 Gratuity Engine**: Added automated 30-day urgent and 60-day warning alerts for Trade License, Establishment Card, Employee Residence Visa, and Emirates ID expiries, alongside a MOHRE/CBUAE 10-field `EDR` + `SCR` WPS `.SIF` generator and a tenure-aware UAE Article 51 End-of-Service Gratuity calculator (21/30-day brackets, unpaid leave exclusion, and 2-year total wage cap).
- **WhatsApp-First Invoicing, Camera Receipt TRN OCR & Executive A4 Print Layout**: Added 1-tap single-language (`EN` or `AR`) WhatsApp invoice and payment link sharing with `+971` mobile normalization, camera receipt 15-digit UAE Vendor TRN and 5% VAT OCR extraction in Direct Expenses, and an isolated A4 executive Tax Invoice print layout with `Dirhams Only.` amount in words.
- **Subscription Plans, Multi-Company Isolation & Bilingual (`EN` / `عربي`) Workspace**: Added self-service onboarding with salted **PBKDF2-SHA256 (120,000 iterations)** credential hashing, Basic/Advance/Premium subscription tiers (**Corporate Tax Only (0% VAT)** pricing), isolated multi-company profile storage, an Owner Admin Console for account management and upgrade approvals, and full English/Arabic RTL interface switching.
- **Direct Expenses & FTA Article 60 Tax Credit Notes**: Added a dedicated **Direct Expenses** workspace with AI receipt scanning and immediate Cash/Bank/Petty Cash settlement, plus sequential **Tax Credit Notes (`CRN-####`)** linked to original customer invoices.
- **UAE PINT-AE UBL 2.1 XML E-Invoicing & FTA Audit File (FAF)**: Upgraded E-Invoice generation to the UAE Peppol **PINT-AE** specification (Invoice `380` and Credit Note `381` with 15-digit TRN validation), expanded **VAT 201** to Emirate-level Boxes `1a`–`1g`, and added **FTA Audit File (`.csv`)** generation.
- **IFRS 15 Deferred Revenue & Usage-Based Recognition**: Added `2150 Deferred Revenue (Contract Liability)` and usage/milestone drawdown recognition alongside straight-line accrual amortization.
- **IndexedDB Attachment Storage & Automatic FX Normalization**: Offloaded binary PDF and image attachments to IndexedDB to prevent browser storage quota limits, and added automatic foreign-currency-to-AED normalization for AI-extracted invoices.
