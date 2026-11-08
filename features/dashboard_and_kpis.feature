@dashboard
Feature: Executive Dashboard KPIs and Financial Breakdown
  As a finance executive using Lumen Accounting Suite
  I want to view real-time cash runway, profit margins, and expense breakdowns across fiscal periods
  So that I can monitor business liquidity and profitability at a glance

  Background:
    Given the bookkeeping application is open on the "Dashboard" view

  @smoke @kpi
  Scenario: Executive dashboard renders hero KPIs, cash flow chart, and clean DOM structure
    When the user selects the dashboard period year "all" and month "all"
    Then the dashboard page title should be "Dashboard"
    And the 6-month cash flow chart should be rendered
    And the dashboard KPI "Total Revenue" should display a formatted currency value
    And the dashboard KPI "Net Profit / (Loss)" should display a formatted currency value
    And the live DOM should contain no unresolved template placeholders

  Scenario Outline: Filtering the executive dashboard by fiscal period updates displayed metrics
    When the user posts a balanced journal entry of "<amount>" AED from "<debit_account>" to "<credit_account>" dated "<entry_date>"
    And the user navigates to the "Dashboard" view
    And the user selects the dashboard period year "<year>" and month "<month>"
    Then the dashboard KPI "<kpi_name>" should reflect a positive balance

    Examples:
      | entry_date | amount  | debit_account       | credit_account       | year | month | kpi_name       |
      | 2026-05-15 | 4000.00 | 1100 Bank Account   | 4100 Service Revenue | 2026 | 4     | Total Revenue  |
      | 2026-06-20 | 1500.00 | 6400 Rent Expense   | 1100 Bank Account    | 2026 | 5     | Total Expenses |

  Scenario: Opening the total expenses breakdown modal displays itemized expense records
    When the user posts a balanced journal entry of "1250.00" AED from "6000 Office Supplies" to "1100 Bank Account" dated "2026-07-10"
    And the user navigates to the "Dashboard" view
    And the user selects the dashboard period year "all" and month "all"
    And the user opens the Total Expenses Breakdown modal
    Then the Total Expenses Breakdown modal should show a non-zero total

  @smoke @auth
  Scenario: Unauthenticated visitors are redirected to /welcome to register and can sign out and sign back in
    When an unauthenticated visitor opens the application root
    Then the browser should redirect to the "/welcome" entrypoint
    And the welcome pricing plans should display Basic at "50" AED and "1 Month Free" promotion on all tiers
    When the visitor registers company "Lumen Advisory" with password "Lumen2026" on the "premium" plan
    Then the dashboard page title should be "Dashboard"
    And the topbar should display the signed-in user email
    When the user signs out from the application topbar
    Then the browser should redirect to the "/welcome" entrypoint
    When the visitor attempts to sign in with password "WrongPassword1"
    Then the sign-in modal should display the error "Incorrect email or password."
    When the visitor attempts to sign in with password "Lumen2026"
    Then the dashboard page title should be "Dashboard"
    And the topbar should display the signed-in user email

  @smoke @i18n
  Scenario: Switching between English and Arabic toggles RTL layout and persists across Main Books App and Welcome page
    When the user toggles the topbar language switcher
    Then the document language should be "ar" with direction "rtl"
    And the dashboard page title should be "لوحة التحكم"
    When a verification screenshot "books_dashboard_arabic_rtl" is captured
    And the user navigates to the "Settings" view
    Then the dashboard page title should be "الإعدادات"
    When a verification screenshot "books_settings_arabic_rtl" is captured
    And the user signs out from the application topbar
    Then the browser should redirect to the "/welcome" entrypoint
    And the document language should be "ar" with direction "rtl"
    And the welcome hero heading should contain "مرحباً بك في"
    When a verification screenshot "welcome_arabic_rtl" is captured
    And the user toggles the topbar language switcher
    Then the document language should be "en" with direction "ltr"
    And the welcome hero heading should contain "Welcome to"
    When a verification screenshot "welcome_english_ltr" is captured

  @legal @admin
  Scenario: Viewing UAE legal modals on /welcome, testing Basic plan feature gating and upgrade request, and approving in Super-Admin Console (/admin)
    When an unauthenticated visitor opens the application root
    Then the browser should redirect to the "/welcome" entrypoint
    When the visitor opens the "terms" legal modal on the Welcome page
    Then the legal modal should display title "Terms of Service" and mention "UAE"
    When the visitor opens the "privacy" legal modal on the Welcome page
    Then the legal modal should display title "Privacy Policy" and mention "PDPL"
    When the visitor opens the "refund" legal modal on the Welcome page
    Then the legal modal should display title "Cancellation" and mention "Cancel"
    When the visitor registers company "Al Noor Retail" with password "Lumen2026" on the "basic" plan
    Then the "Quotes & Estimates" navigation item should be locked with a plan badge
    And physical localStorage should contain only UI configuration keys
    When the user navigates to the "Expenses" view
    And the user records a direct expense for payee "DEWA Utility" of "400.00" AED on "6000 Office Supplies" paid from "1005 Bank" in "Dubai" with "standard" VAT
    And the user navigates to the "Settings" view
    And the customer submits a plan upgrade request from Settings
    Then the Settings Subscription Plan card should display "Upgrade requested: Advance (Pending Admin Approval)"
    When the administrator signs in to the Super-Admin Console with email "admin@lumenconsultancy.net" and password "LumenAdmin2026"
    Then the Super-Admin Console should display MRR metrics and list the registered company with a pending upgrade
    When the administrator approves the pending upgrade request for the registered company
    Then the Super-Admin Console should show no pending upgrade request for the registered company
    When the administrator opens the customer books for the registered company from the Super-Admin Console
    And the user navigates to the "Expenses" view
    Then the Expense History table should list payee "DEWA Utility" with VAT "20.00" and total "420.00"

  @smoke @corp_tax_tracker
  Scenario: Live 9% UAE Corporate Tax and Small Business Relief tracker updates on the Home Dashboard
    When the user posts a balanced journal entry of "200000.00" AED from "1100 Bank Account" to "4100 Service Revenue" dated "2026-08-01"
    And the user navigates to the "Dashboard" view
    And the user selects the dashboard period year "2026" and month "7"
    Then the dashboard UAE Corporate Tax tracker should show regime status "0% Bracket" and estimated tax "0.00"
    When the user posts a balanced journal entry of "300000.00" AED from "1100 Bank Account" to "4100 Service Revenue" dated "2026-08-15"
    And the user navigates to the "Dashboard" view
    And the user selects the dashboard period year "2026" and month "7"
    Then the dashboard UAE Corporate Tax tracker should show regime status "9% Standard Bracket" and estimated tax "11,250.00"
    And the dashboard UAE Corporate Tax tracker Small Business Relief status should contain "Eligible"

  @smoke @compliance_reminders
  Scenario: UAE Compliance Reminder widget on the Home Dashboard alerts on Trade License, Establishment Card, and Employee Visa/Emirates ID expiries
    When the user navigates to the "Settings" view
    And the user configures UAE compliance renewal dates with Trade License "DED-88441" expiring in "15" days and Establishment Card "EST-99110" expiring in "90" days
    And the user navigates to the "Employee details" view
    And the user adds an employee "Layla Al Hashimi" with position "Operations Manager", basic salary "12000", Visa expiring in "-5" days, and Emirates ID expiring in "25" days
    And the user navigates to the "Dashboard" view
    Then the dashboard UAE Compliance Reminder widget should show Trade License status containing "Due in 15d" and Establishment Card status containing "Valid"
    And the dashboard UAE Compliance Reminder widget should list employee "Layla Al Hashimi" with "Expired" and "Due in 25d" alerts
