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
    When the user navigates to the "Settings" view
    And the customer submits a plan upgrade request from Settings
    Then the Settings Subscription Plan card should display "Upgrade requested: Advance (Pending Admin Approval)"
    When the administrator signs in to the Super-Admin Console with email "admin@lumenconsultancy.net" and password "LumenAdmin2026"
    Then the Super-Admin Console should display MRR metrics and list the registered company with a pending upgrade
    When the administrator approves the pending upgrade request for the registered company
    Then the Super-Admin Console should show no pending upgrade request for the registered company

