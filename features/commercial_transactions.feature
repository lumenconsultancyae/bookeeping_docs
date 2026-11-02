@commercial
Feature: Commercial Transactions, AI Document Extraction, Quotes, Purchase Orders, and Banking
  As a commercial accountant using Lumen Accounting Suite
  I want to issue UAE E-Invoices, extract Supplier Bills with AI, convert Quotes and Purchase Orders, and automate Bank Rules
  So that order-to-cash, procure-to-pay, and bank reconciliation workflows run end-to-end

  Background:
    Given the bookkeeping application is open on the "Dashboard" view

  @smoke @einvoice
  Scenario: Generating a standard-rated UAE Customer E-Invoice calculates 5% VAT and updates Statement of Account
    When the user navigates to the "Sales Invoices" view
    And the user fills a customer invoice for "Crescent Ventures LLC" with item "Cloud Architecture Retainer" quantity "2" at rate "3000.00" AED and "standard" VAT
    Then the customer invoice summary should show subtotal "6,000.00", VAT "300.00", and total "6,300.00"
    When the user previews the customer E-Invoice
    Then the E-Invoice preview modal should display "TAX INVOICE" and the customer name
    When the user submits the customer invoice to the ledger
    And the user navigates to the "Statement of Account" view
    And the user loads the Statement of Account for "ALL_AR"
    Then the Statement of Account should list the customer invoice with a positive receivable balance

  @ai
  Scenario: Uploading a Supplier Bill uses AI extraction and posts the reviewed bill to the General Ledger
    When the user navigates to the "Supplier Bills" view
    And the user uploads and analyzes a sample supplier invoice document
    Then the AI extraction review card should populate supplier "Gulf Cloud Infrastructure LLC" and total "2100.00"
    When the user confirms and saves the extracted supplier bill to the ledger
    And the user navigates to the "General Ledger" view
    Then the General Ledger should contain the supplier bill for "Gulf Cloud Infrastructure LLC"

  @ai @pdf
  Scenario: Uploading a multi-line PDF Supplier Tax Invoice extracts pre-tax line items, VAT, and total accurately
    When the user navigates to the "Supplier Bills" view
    And the user uploads and analyzes a sample supplier invoice PDF document
    Then the AI extraction review card should populate supplier "Meydan Free Zone", tax "17.86", and total "12520.00"
    When the user confirms and saves the extracted supplier bill to the ledger
    And the user navigates to the "General Ledger" view
    Then the General Ledger should contain the supplier bill for "Meydan"

  Scenario: Creating a pre-sales Quote and converting it to a Sales Invoice
    Given an inventory item "Managed Firewall Appliance" with SKU "FW-900" priced at "1500.00" AED exists
    When the user navigates to the "Quotes & Estimates" view
    And the user creates a quote for client "Falcon FinTech PJSC" with SKU "FW-900" quantity "2" at price "1500.00" AED
    Then the Quotes history table should list the quote with status "Draft"
    When the user converts the quote to a sales invoice
    Then the Quotes history table should list the quote with status "Invoiced"

  Scenario: Creating a Purchase Order, receiving goods, and performing 3-way match billing
    Given an inventory item "NVMe Storage Server" with SKU "SRV-NVME" and initial quantity "5" at unit cost "4000.00" AED exists
    When the user navigates to the "Purchase Orders" view
    And the user creates a purchase order for supplier "Silicon Oasis Hardware LLC" with SKU "SRV-NVME" quantity "4" at cost "4000.00" AED
    Then the Purchase Orders history table should list the purchase order with status "Draft"
    When the user marks the purchase order goods as received
    Then the Purchase Orders history table should list the purchase order with status "Goods Received"
    When the user converts the purchase order to a supplier bill
    Then the Purchase Orders history table should list the purchase order with status "Billed"

  Scenario: Configuring a Bank Rule, connecting automated bank feeds, and scheduling a Recurring Transaction
    When the user navigates to the "Banking" view
    And the user creates a bank rule named "DEWA Auto Rule" matching keyword "DEWA" to account "6100 Utilities" with "5" percent VAT
    Then the Bank Rules table should list the rule "DEWA Auto Rule"
    When the user connects the automated bank feed
    Then the Automated Bank Feeds table should display imported feed transactions
    When the user navigates to the "Recurring Transactions" view
    And the user adds a "monthly" recurring "Bill" template named "Monthly Data Center Colocation" for "Etisalat Digital" of "4500.00" AED starting "2026-12-01"
    Then the Recurring Transactions table should list "Monthly Data Center Colocation"
