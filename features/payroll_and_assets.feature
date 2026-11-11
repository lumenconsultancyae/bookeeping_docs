@payroll @assets
Feature: Employee Directory, UAE WPS Payroll, Gratuity (EOSB), and Fixed Assets
  As an HR and payroll controller using Lumen Accounting Suite
  I want to manage employees, process monthly WPS payroll runs with EOSB gratuity accruals, and track fixed asset depreciation
  So that staff compensation, statutory UAE gratuity liabilities, and capital assets are properly accounted for

  Background:
    Given the bookkeeping application is open on the "Dashboard" view

  @smoke @wps
  Scenario: Adding an employee, processing a monthly WPS payroll run, and calculating EOSB gratuity
    When the user navigates to the "Settings" view
    And the user configures company branding with name "Lumen Management Consultancy", address "Business Bay, Dubai, UAE", contact number "+971 56 471 8587", and a company logo
    When the user navigates to the "Employee details" view
    And the user adds an employee named "Tariq Al Mansoori" as "Principal Systems Architect" hired on "2024-01-15" with basic salary "15000", transportation allowance "2000", and accommodation "3000"
    And the user adds an employee named "Layla Al Qasimi" as "Finance Controller" hired on "2023-05-01" with basic salary "18000" and housing allowance "6000"
    And the user adds an employee named "Temporary Contractor" as "Consultant" hired on "2024-06-01" with basic salary "9000" and housing allowance "1000"
    Then the Employee Directory should list "Tariq Al Mansoori" with hired date "15/01/2024" and total pay "20,000.00"
    When a verification screenshot "employee_directory_dd_mm_yyyy" is captured
    When the user navigates to the "Timesheet & WPS" view
    Then the Timesheet employee filter dropdown should include both "Tariq Al Mansoori" and "Layla Al Qasimi"
    When the user processes and saves the payroll run for period "2026-10" paid from "1100 Bank Account" with EOSB accrual enabled after deleting employee "Temporary Contractor" from the timesheet
    Then the saved timesheets section for "2026-10" should list "Tariq Al Mansoori"
    When the user filters the saved timesheets by employee "Tariq Al Mansoori"
    Then the filtered timesheets section for "2026-10" should list "Tariq Al Mansoori" and exclude "Layla Al Qasimi"
    When the user filters the saved timesheets by employee "All Employees"
    When the user opens the payslip for "Tariq Al Mansoori" in period "2026-10"
    Then the professional payslip document should display employee "Tariq Al Mansoori", designation "Principal Systems Architect", starting date "15/01/24", company "Lumen Management Consultancy", address "Business Bay, Dubai, UAE", contact number "+971 56 471 8587", and the company logo
    And the EOSB Summary should display an accrued gratuity balance for "Tariq Al Mansoori"
    And the WPS SIF preview should contain an "EDR" record and a MOHRE "SCR" control record for "102026"
    When the user simulates statutory gratuity for basic salary "12000" AED, total salary "16000" AED, hired "2019-11-07", ending "2026-11-05" with "0" unpaid leave days
    Then the statutory gratuity calculator should show "> 5 Yrs (30 Days/Yr)" and statutory entitlement "66,000.00"
    When the user navigates to the "Profit & Loss" view
    Then the Income Statement should display "6500 Payroll / Salaries" and "44,000.00"
    When the user navigates to the "Timesheet & WPS" view
    And the user deletes the saved timesheet for period "2026-10" from the Edit Details modal
    Then the saved timesheets section for "2026-10" should not list "Tariq Al Mansoori"

  Scenario: Fixed Assets directory computes monthly straight-line depreciation and net book value
    When the user navigates to the "Assets Directory" view
    And a fixed asset "Executive Conference A/V System" located in "Dubai HQ" purchased on "2026-01-01" for "36000.00" AED over "3" years is registered
    Then the Fixed Assets Directory should list "Executive Conference A/V System" with monthly depreciation "1,000.00"
