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
- **UAE PINT-AE XML E-Invoicing**: Click **Preview E-Invoice** to print a formatted UAE Tax Invoice or export a validated **UAE Peppol PINT-AE UBL 2.1 XML** document (Invoice `380` or Tax Credit Note `381` with 15-digit TRN validation).
- **Tax Credit Notes (FTA Article 60)**: Issue a linked **Tax Credit Note (`CRN-####`)** against any posted sales invoice to record returns, discounts, or billing adjustments, automatically reversing Output VAT, revenue, and open customer receivables.

### Supplier Bills & Direct Expenses
- **Supplier Bills (`TRANSACTIONS > Supplier Bills`)**: Drag and drop a PDF, PNG, or JPG vendor invoice and click **Analyze Document**. Review extracted line items, foreign currency conversion to AED, and suggested accounts, optionally flag items as **Corporate Tax Add-Back**, and click **Confirm & Save to Ledger**.
- **Direct Expenses (`TRANSACTIONS > Expenses`)**: Record immediate out-of-pocket or card/bank expenses (or scan receipts with AI) paid directly from **Cash**, **Bank**, **Petty Cash**, or **Accounts Payable**, with built-in VAT calculation and Corporate Tax Add-Back flagging.

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

### Payroll, Timesheets & UAE WPS
Navigate to **PAYROLL > Employee details** and **PAYROLL > Timesheet & WPS**:
- Maintain employee records including Employee ID, Labour Card Number, IBAN, Bank Routing Code, Basic Salary, Housing, Telephone, and Other Allowances.
- Open the monthly **Timesheet (UAE WPS)** modal to record days worked, bonuses, loan deductions, and other deductions, and optionally accrue **End of Service Benefits (EOSB)** and leave salary.
- Click **Save Payroll** to post all payroll journal entries automatically, generate printable employee **Payslips**, and click **Download WPS (.sif)** to export a UAE Wage Protection System Salary Information File.

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
  - Switch between multiple company profiles, toggle the interface between **English (`EN`)** and **Arabic (`عربي`)** with Right-to-Left (RTL) layout, manage your subscription plan (**Basic** AED 35/mo, **Advance** AED 75/mo, **Premium** AED 100/mo — **Corporate Tax Only (0% VAT)**) secured by salted **PBKDF2-SHA256 (120,000 iterations)** password hashing, and inspect the **Audit Log** for a chronological compliance record of system creations, updates, and deletions.

---

## Release Notes

### Latest Release Highlights

- **Subscription Plans, Multi-Company Isolation & Bilingual (`EN` / `عربي`) Workspace**: Added self-service onboarding with salted **PBKDF2-SHA256 (120,000 iterations)** credential hashing, Basic/Advance/Premium subscription tiers (**Corporate Tax Only (0% VAT)** pricing), isolated multi-company profile storage, an Owner Admin Console for account management and upgrade approvals, and full English/Arabic RTL interface switching.
- **Direct Expenses & FTA Article 60 Tax Credit Notes**: Added a dedicated **Direct Expenses** workspace with AI receipt scanning and immediate Cash/Bank/Petty Cash settlement, plus sequential **Tax Credit Notes (`CRN-####`)** linked to original customer invoices.
- **UAE PINT-AE UBL 2.1 XML E-Invoicing & FTA Audit File (FAF)**: Upgraded E-Invoice generation to the UAE Peppol **PINT-AE** specification (Invoice `380` and Credit Note `381` with 15-digit TRN validation), expanded **VAT 201** to Emirate-level Boxes `1a`–`1g`, and added **FTA Audit File (`.csv`)** generation.
- **IFRS 15 Deferred Revenue & Usage-Based Recognition**: Added `2150 Deferred Revenue (Contract Liability)` and usage/milestone drawdown recognition alongside straight-line accrual amortization.
- **IndexedDB Attachment Storage & Automatic FX Normalization**: Offloaded binary PDF and image attachments to IndexedDB to prevent browser storage quota limits, and added automatic foreign-currency-to-AED normalization for AI-extracted invoices.
