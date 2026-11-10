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

  @art59 @einvoice
  Scenario: Issuing an Art. 59 Tax Invoice with Date of Supply, line discount, and per-line VAT followed by a Tax Credit Note (CRN-####)
    When the user navigates to the "Sales Invoices" view
    And the user fills an Art. 59 customer invoice for "Al Masa Advisory LLC" issued "2026-10-10" supplied "2026-10-05" with item "VAT Compliance Audit" quantity "2" at rate "1000.00" AED discount "200.00" AED and "standard" VAT
    Then the customer invoice summary should show discount "200.00", subtotal "1,800.00", VAT "90.00", and total "1,890.00"
    When the user previews the customer E-Invoice
    Then the E-Invoice preview modal should display Invoice Date "10/10/26", Terms, Due Date, Discount, VAT Rate, and VAT Amount
    When the user submits the customer invoice to the ledger
    And the user issues a Tax Credit Note against the last invoice with reason "Agreed Price / Discount Adjustment", item "Partial Scope Credit", quantity "1", rate "500.00" AED, discount "50.00" AED, and "5" percent VAT
    Then the Tax Credit Note summary should show discount "50.00", subtotal "450.00", VAT "22.50", and total "472.50"
    When the user previews and submits the Tax Credit Note to the ledger
    And the user navigates to the "Statement of Account" view
    And the user loads the Statement of Account for "ALL_AR"
    Then the Statement of Account should list both the customer invoice and the Tax Credit Note

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

  @expenses
  Scenario: Recording and editing a direct business expense in the Expenses module updates Expense History and General Ledger
    When the user navigates to the "Expenses" view
    And the user records a direct expense for payee "ENOC Retail LLC" of "400.00" AED on "6000 Office Supplies" paid from "1005 Bank" in "Dubai" with "standard" VAT
    Then the Expense History table should list payee "ENOC Retail LLC" with VAT "20.00" and total "420.00"
    When the user edits the last recorded expense amount to "500.00" AED with 5% VAT
    Then the Expense History table should list payee "ENOC Retail LLC" with VAT "25.00" and total "525.00"

  @whatsapp_workflows
  Scenario: Sharing a bilingual AR/EN Tax Invoice + Payment Link via WhatsApp and snapping a camera receipt for Vendor TRN OCR
    When the user navigates to the "Sales Invoices" view
    And the user fills a WhatsApp-ready customer invoice for "Al Noor Logistics LLC" with phone "050 123 4567" and payment link "https://pay.ziina.com/lumen/INV-WA" for "Express Freight" quantity "1" at rate "2000.00" AED
    And the user previews the customer E-Invoice
    Then the bilingual E-Invoice preview should display "فاتورة ضريبية", payment link "https://pay.ziina.com/lumen/INV-WA", and a 1-tap WhatsApp share URL for "971501234567"
    When the user navigates to the "Expenses" view
    And the user snaps a camera receipt photo in the Expenses module for OCR extraction
    Then the Expense OCR form should auto-populate Vendor TRN "100234567890003", payee "ADNOC Distribution", net "200.00", and VAT "10.00"
    When the user saves the OCR-extracted expense
    Then the Expense History table should display Vendor TRN "100234567890003" and total "210.00"
