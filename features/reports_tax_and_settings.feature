@reports @tax
Feature: Financial Statements, UAE VAT 201, Corporate Tax, Budgeting, Forecast, Audit Log, and Settings
  As a chief financial officer using Lumen Accounting Suite
  I want to generate balanced financial statements, file UAE VAT 201 and Corporate Tax returns, track budgets and 90-day cash forecasts, and audit system settings
  So that the enterprise meets UAE Federal Tax Authority compliance and financial governance standards

  Background:
    Given the bookkeeping application is open on the "Dashboard" view

  @smoke @financial-statements
  Scenario: Trial Balance remains in double-entry equilibrium and populates financial statements
    When the user navigates to the "Sales Invoices" view
    And the user fills a customer invoice for "Marina Retail Group" with item "POS Integration Suite" quantity "1" at rate "10000.00" AED and "standard" VAT
    And the user submits the customer invoice to the ledger
    And the user navigates to the "Trial Balance" view
    Then the Trial Balance total debits should equal total credits
    When the user navigates to the "Profit & Loss" view
    Then the Income Statement should display "Total Revenue" and "Net Income"
    When the user navigates to the "Balance Sheet" view
    Then the Balance Sheet should display "Total Assets" and "Total Liabilities & Equity"
    When the user navigates to the "Cash Flow" view
    Then the Cash Flow Statement should display "Operating Activities" and "Net Change in Cash"
    When the user navigates to the "Statement of Equity" view
    Then the Statement of Equity should display "Beginning Equity" and "Ending Equity"

  Scenario: UAE VAT 201 return and Corporate Tax summary reflect standard-rated supplies and non-deductible add-backs
    When the user navigates to the "Journal Entries" view
    And the user prepares a journal entry for "1000.00" AED debiting "6900 Miscellaneous Expense" and crediting "1100 Bank Account" with "exempt" VAT flagged as a Corporate Tax Add-Back
    And the user submits the prepared journal entry
    And the user navigates to the "VAT" view
    Then the UAE VAT Return Summary should display formatted Output VAT, Input VAT, and Net VAT values
    When the user clicks the "Export FTA Audit File (FAF)" button in the Tax module
    Then the exported FTA Audit File CSV should contain Company Header, Master Data, Purchase Lines, Sales Lines, and balanced General Ledger entries
    When the user navigates to the "Corporate Tax" view
    Then the UAE Corporate Tax Summary should reflect a positive Add-Backs balance

  Scenario: Setting a monthly expense budget evaluates variance status and 90-day Cash Flow Forecast projects balances
    When the user posts a balanced journal entry of "800.00" AED from "6000 Office Supplies" to "1100 Bank Account" dated "2026-08-15"
    And the user navigates to the "Budgeting vs. Actuals" view
    And the user sets a monthly budget for period "2026-08" on account "6000 Office Supplies" of "2000.00" AED
    Then the Budgeting vs. Actuals table should show account "6000 Office Supplies" with status "Under Budget"
    When the user navigates to the "Cash Flow Forecast" view
    Then the 90-day Cash Flow Forecast table should display "Starting Balance (Bank & Cash)"

  Scenario: Updating Company Letterhead, UAE Tax Relief, and Multi-Currency Rates and verifying the System Audit Trail
    When the user posts a balanced journal entry of "500.00" AED from "6000 Office Supplies" to "1100 Bank Account" dated "2026-09-01"
    And the user navigates to the "Settings" view
    And the user saves company letterhead settings for "Lumen Advisory FZ-LLC" with TRN "100334455667703" and IBAN "AE070331234567890123456"
    And the user saves UAE tax settings for company type "Mainland" with Small Business Relief enabled
    And the user adds or updates the currency exchange rate for "EUR" to "4.0250" AED
    Then the Currency Exchange Rates table should list "EUR" with rate "4.025"
    When the user navigates to the "Audit Log" view
    Then the System Audit Trail should contain a "Create" entry for "Saved transaction"

  @vat201
  Scenario: UAE VAT 201 Emirate Boxes 1a and 1b and Box 3 Reverse Charge populate from Emirate sales and RCM expenses
    When the user posts a standard-rated sales invoice in "Abu Dhabi" for "ADNOC Logistics PJSC" of "4000.00" AED
    And the user posts a standard-rated sales invoice in "Dubai" for "Emaar Hospitality LLC" of "6000.00" AED
    And the user navigates to the "Expenses" view
    And the user records a direct expense for payee "AWS EMEA SARL" of "2000.00" AED on "6200 Software & SaaS" paid from "1005 Bank" in "Dubai" with "reverse_charge" VAT
    And the user navigates to the "VAT" view
    Then the VAT 201 return should show positive output VAT in Box 1a (Abu Dhabi) and Box 1b (Dubai) and positive Box 3 Reverse Charge

  @fx
  Scenario: Converting legacy foreign-currency supplier bills to AED and undoing the conversion in Settings
    When a legacy unconverted supplier bill "SUP-FX" for "Global Cloud Corp" of "1000.00" in foreign currency exists
    And the user navigates to the "Settings" view
    And the user adds or updates the currency exchange rate for "USD" to "3.6725" AED
    And the user converts the legacy supplier bill from "USD" to AED in Settings
    Then the FX conversion status message should contain "converted to AED"
    When the user undoes the last FX conversion in Settings
    Then the FX conversion status message should contain "Last conversion undone"

