@payroll @assets
Feature: Employee Directory, UAE WPS Payroll, Gratuity (EOSB), and Fixed Assets
  As an HR and payroll controller using Lumen Accounting Suite
  I want to manage employees, process monthly WPS payroll runs with EOSB gratuity accruals, and track fixed asset depreciation
  So that staff compensation, statutory UAE gratuity liabilities, and capital assets are properly accounted for

  Background:
    Given the bookkeeping application is open on the "Dashboard" view

  @smoke @wps
  Scenario: Adding an employee, processing a monthly WPS payroll run, and calculating EOSB gratuity
    When the user navigates to the "Employee details" view
    And the user adds an employee named "Tariq Al Mansoori" as "Principal Systems Architect" hired on "2024-01-15" with basic salary "15000" and housing allowance "5000"
    Then the Employee Directory should list "Tariq Al Mansoori" with total pay "20,000.00"
    When the user navigates to the "Timesheet & WPS" view
    And the user processes and saves the payroll run for period "2026-10" paid from "1100 Bank Account" with EOSB accrual enabled
    Then the saved timesheets section for "2026-10" should list "Tariq Al Mansoori"
    And the EOSB Summary should display an accrued gratuity balance for "Tariq Al Mansoori"

  Scenario: Fixed Assets directory computes monthly straight-line depreciation and net book value
    When the user navigates to the "Assets Directory" view
    And a fixed asset "Executive Conference A/V System" located in "Dubai HQ" purchased on "2026-01-01" for "36000.00" AED over "3" years is registered
    Then the Fixed Assets Directory should list "Executive Conference A/V System" with monthly depreciation "1,000.00"
