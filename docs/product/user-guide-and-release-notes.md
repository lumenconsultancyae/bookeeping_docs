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

### Fixed Assets & Accruals
- **Fixed Assets (`ASSETS > Assets Directory`)**: Track capital equipment and property with purchase dates, locations, initial values, and useful life in years. The suite automatically generates monthly straight-line depreciation entries and computes accumulated depreciation and net book value.
- **Accruals & Prepayments (`ACCOUNTING > Accruals`)**: Register prepaid expenses (such as annual office rent or software subscriptions) with a start date, total amount, and amortization life in months. First-month amortization is automatically pro-rated by active days, and you can inspect the full amortization timetable via **View Schedule**.

---

## Commercial Transactions & AI Document Capture

### Quotes & Purchase Orders
- **Quotes & Estimates (`TRANSACTIONS > Quotes & Estimates`)**: Create pre-sales quotes for clients using inventory items. Once approved by the client, click **Convert to Invoice** to automatically generate a sales invoice in the ledger.
- **Purchase Orders (`TRANSACTIONS > Purchase Orders`)**: Issue purchase orders to suppliers, mark shipments via **Receive Goods**, and complete procurement using **3-Way Match & Bill** to convert received purchase orders directly into supplier bills.

### Sales Invoices & UAE E-Invoicing
Navigate to **TRANSACTIONS > Sales Invoices** to bill customers:
- **AI Auto-Fill (Optional)**: Upload an existing PDF or image invoice to automatically populate customer details, line items, and tax treatment.
- **Manual Generation**: Select or enter a customer name, payment terms, revenue account (`Service Revenue`, `Product Sales`, `Consulting Income`, or `Other Revenue`), line items, and tax treatment (**Standard 5%**, **Zero-Rated 0%**, or **Exempt**).
- Selling an inventory item under `Product Sales` automatically deducts stock in the **Stock Ledger** and posts a corresponding **Cost of Goods Sold (COGS)** entry.
- Click **Preview E-Invoice** to inspect or print a formatted UAE Tax Invoice or download a PEPPOL-compliant **UBL 2.1 XML E-Invoice**.

### Supplier Bills & Expenses
Navigate to **TRANSACTIONS > Supplier Bills** to process vendor invoices with **Lumy AI**:
- Drag and drop a PDF, PNG, or JPG invoice and click **Analyze Document**.
- Review the extracted invoice number, date, supplier name, TRN, currency, line items, and suggested expense/asset accounts.
- Flag non-deductible expenses (such as fines or client entertainment) using **Flag as Corporate Tax Add-Back**.
- Click **Confirm & Save to Ledger** to post the bill (automatically converting foreign currencies to AED using your configured exchange rates).

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
- **UAE VAT & Corporate Tax (`TAX > VAT` & `Corporate Tax`)**:
  - Generate FTA **VAT201** return summaries (Boxes 1 through 14) showing output tax, recoverable input tax, and net payable/refundable VAT.
  - Review **UAE Corporate Tax** calculations showing Net Profit, non-deductible Add-Backs, Adjusted Taxable Income, and estimated 9% Corporate Tax above the AED 375,000 threshold (respecting Mainland vs. Qualifying Free Zone and Small Business Relief settings).
- **FP&A (`FP&A > Budgeting vs. Actuals` & `Cash Flow Forecast`)**:
  - Set monthly account budgets and monitor real-time variances (`Target Met`, `Under Target`, `Under Budget`, `Over Budget`).
  - View a 90-day **Cash Flow Forecast** projecting your running cash balance from open receivables and payables by due date.
- **Financial Reports (`REPORTS`) & Audit Log**:
  - Generate real-time **Profit & Loss**, **Balance Sheet**, **Cash Flow**, **Statement of Equity**, and **Trial Balance** statements.
  - Inspect the **Audit Log** for a chronological compliance record of system creations, updates, and deletions.

---

## Release Notes

### Latest Release Highlights

- **Multi-Page PDF AI Document Extraction**: Uploaded multi-page PDF supplier bills, customer invoices, and petty cash receipts are now stitched and analyzed across all pages so line items and totals on continuation pages are captured completely.
- **Configurable AI Integration & Resilient Parsing**: Added an **AI Integration Settings** panel under **Settings** to configure custom AI prediction endpoints, paired with resilient JSON extraction and clear fallback prompts when unstructured responses are returned.
- **Semantic Expense Classification**: AI document extraction now classifies line items into **OpEx**, **COGS**, or **Capitalized R&D** based on business context in addition to mapping each item to the Chart of Accounts.
- **Enhanced UAE VAT & Corporate Tax Controls**: Added **Company Type** (**Mainland** vs. **Qualifying Free Zone**) and **Small Business Relief** configuration under **Settings**, transaction-level VAT treatment toggles (**Standard 5%**, **Zero-Rated 0%**, **Exempt**), and **Corporate Tax Add-Back** flags on supplier bills and journal entries.
- **Statement of Account KPI Summary Cards**: Redesigned the **Statement of Account** view with top-level summary cards for **Total Invoice Value**, **Total Payments**, and **Balance** alongside `All Accounts Payable` and `All Accounts Receivable` modes.
- **Customer Invoice Revenue & Full Ledger Editing**: Updated Revenue KPI calculations to include posted, paid, and partially paid customer invoices accurately, and enabled full editing of date, entity, reference, subtotal, tax, total, and account fields inside the **Edit Ledger Entry** modal.
- **Banking View Stability**: Resolved an input initialization issue when switching to the **Banking** workspace view.
