@accounting
Feature: Chart of Accounts, Manual Journal Entries, Accruals, and Period Locking
  As an accountant using Lumen Accounting Suite
  I want to manage accounts, post double-entry journals, amortize prepaid expenses, and lock closed fiscal periods
  So that the General Ledger remains accurate and compliant with audit controls

  Background:
    Given the bookkeeping application is open on the "Dashboard" view

  @smoke @coa
  Scenario: Adding a custom account to the Chart of Accounts persists in the directory
    When the user navigates to the "Chart of Accounts" view
    And the user adds a custom account with code "6850" named "Cloud AI Infrastructure" of type "Expense"
    Then the Chart of Accounts table should list the custom account "Cloud AI Infrastructure"

  Scenario: Previewing and posting a standard-rated manual journal entry updates the General Ledger
    When the user navigates to the "Journal Entries" view
    And the user prepares a journal entry for "2000.00" AED debiting "6000 Office Supplies" and crediting "1100 Bank Account" with "standard" VAT
    And the user previews the journal posting
    Then the journal posting preview should include "6000 Office Supplies"
    When the user submits the prepared journal entry
    And the user navigates to the "General Ledger" view
    Then the General Ledger should contain the posted journal entry

  Scenario: Creating a prepaid accrual schedule calculates monthly amortization and generates a schedule
    When the user navigates to the "Accruals" view
    And the user creates a prepaid accrual for "Annual Warehouse Lease" of "12000.00" AED over "12" months starting "2026-01-01"
    Then the Accruals directory should list the schedule for "Annual Warehouse Lease" with monthly amortization "1,000.00"
    And the accrual amortization schedule modal for "Annual Warehouse Lease" should contain "12" monthly installments

  Scenario: Locking the General Ledger prevents deletion of entries in the closed period
    When the user posts a balanced journal entry of "950.00" AED from "6400 Rent Expense" to "1100 Bank Account" dated "2026-02-10"
    And the user navigates to the "General Ledger" view
    And the user locks the General Ledger up to "2026-03-31"
    And the user attempts to delete the locked journal entry from the General Ledger
    Then the system should block the deletion with a closed period warning
    And the General Ledger should still contain the locked journal entry

  @accrual @usage
  Scenario: Tracking 2150 Deferred Revenue with Usage / Drawdown recognition updates accumulated and remaining balances
    When the user navigates to the "Accruals" view
    And the user creates a usage-based accrual schedule for "Annual Cloud Retainer Advance" of "6000.00" AED debiting "2150 Deferred Revenue / Customer Advances" and crediting "4100 Service Revenue" starting "2026-01-01"
    And the user records a usage drawdown of "1500.00" AED on "Annual Cloud Retainer Advance" dated "2026-06-15" with note "Phase 1 Milestone Delivered"
    Then the Accruals directory should show "Annual Cloud Retainer Advance" with accumulated recognition "1,500.00" and net balance "4,500.00"

