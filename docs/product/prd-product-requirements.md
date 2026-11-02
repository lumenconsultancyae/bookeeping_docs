# Product Requirements Document (PRD): Lumen Accounting Suite

## Purpose & Product Scope

Lumen Accounting Suite provides UAE small and medium-sized enterprises (SMEs) with a unified, browser-accessible bookkeeping, commercial operations, payroll, and tax compliance application. This PRD defines the current short-term product deliverable scope separately from the target architecture delta documented in the companion Software Design Document (SDD).

---

## Target Personas

- **Chief Executive Officer / Founder**: Monitors Cash Runway, 90-day Monthly Burn, Net Profit Margin, 6-month Cash Flow trends, and 30+ day overdue receivables/payables from the executive dashboard.
- **Bookkeeper / Accountant**: Captures supplier bills, customer invoices, petty cash receipts, and bank statements; manages the Chart of Accounts, Accruals, Fixed Assets, and General Ledger; and locks completed monthly periods.
- **Operations & HR Manager**: Manages Customer and Supplier directories, Inventory items and Stock Ledger movements, Quotes, Purchase Orders, Employee profiles, monthly UAE WPS payroll runs, and End of Service Benefit (EOSB) accruals.
- **Tax & Compliance Officer**: Generates UAE FTA VAT201 return summaries, computes UAE Corporate Tax liabilities (accounting for non-deductible add-backs, Mainland vs. Qualifying Free Zone status, and Small Business Relief), exports PEPPOL UBL 2.1 XML E-Invoices, and reviews the immutable System Audit Trail.

---

## Functional Requirements (Delivered Scope)

| Functional Area | Requirement Summary | Acceptance Criteria |
| :--- | :--- | :--- |
| **Executive Dashboard** | Display hero KPIs (Cash Runway, Burn Rate, Net Profit Margin, Current Cash), 6-month Cash Flow bar chart, overdue AR/AP hit lists, and detailed accounting KPIs with period filtering. | Selecting a Year/Month updates P&L metrics for that period and Balance Sheet metrics cumulatively up to that period; clicking KPI cards filters the General Ledger. |
| **AI Document Capture** | Extract structured fields and line items from multi-page PDF and image Supplier Bills, Customer Invoices, Petty Cash Receipts, and Bank Statements. | All PDF pages are rasterized and submitted to the configured AI endpoint; extracted line items map to Chart of Accounts codes and semantic categories (`OpEx`, `COGS`, `Capitalized R&D`). |
| **Commercial Workflows** | Support end-to-end Quote-to-Invoice and Purchase-Order-to-Bill (3-Way Match) lifecycles, Customer E-Invoicing (print + UBL 2.1 XML), and Cheque Registry tracking. | Converting a Quote creates a Sales Invoice; receiving and matching a PO creates a Supplier Bill; Customer Invoices support Standard (5%), Zero-Rated (0%), and Exempt VAT treatments. |
| **Double-Entry Accounting** | Provide a configurable Chart of Accounts, manual Journal Entries with posting preview, General Ledger filtering/editing, payment-to-invoice matching, Statement of Account (SOA), and Close Month period locking. | Closing a month locks all entries on or before the lock date against deletion or backdated posting; SOA displays Total Invoice Value, Total Payments, and Running Balance. |
| **Automated Schedules** | Synthesize monthly depreciation entries for Fixed Assets, pro-rated amortization entries for Accruals/Prepayments, and scheduled Recurring Transactions. | Active assets and accruals automatically generate monthly journal vouchers up to the current date without manual intervention. |
| **Inventory & COGS** | Maintain an Inventory Directory with bidirectional Cost/Markup/Price calculation and a chronological Stock Ledger. | Saving a new item with initial stock logs an `IN` movement; invoicing a product logs an `OUT` movement and posts a `5000 Cost of Goods Sold` / `1300 Inventory` journal entry. |
| **Payroll & UAE WPS** | Manage Employee salary structures, process monthly timesheets, post multi-legged payroll and EOSB/leave journals, print payslips, and export `.sif` WPS files. | Saving payroll posts Gross Pay, Net Pay, Loan/Other Deductions, and optional EOSB/Leave accruals (`21 days/year` basic salary formula) and generates a downloadable `WPS_<YYYY-MM>.sif` file. |
| **Tax, FP&A & Reporting** | Render Trial Balance, Income Statement, Balance Sheet, Cash Flow, Statement of Equity, FTA VAT201 Boxes 1–14, UAE Corporate Tax (9% over AED 375,000), Monthly Budgeting vs. Actuals, and 90-Day Cash Flow Forecast. | Corporate Tax adds back flagged non-deductible expenses and applies 0% when Qualifying Free Zone or Small Business Relief is enabled. |
