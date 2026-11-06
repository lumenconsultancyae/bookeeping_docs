@ux
Feature: Professional interaction patterns — confirmations, inline validation, pagination and responsive navigation
  As a bookkeeper using Lumen Books on a desktop, tablet or phone
  I want non-blocking notifications, inline form errors, paginated lists and drawer navigation
  So that I can work quickly without native browser pop-ups or scrolling through endless pages

  Background:
    Given the bookkeeping application is open on the "Dashboard" view

  @smoke
  Scenario: Long customer directories are paginated and searchable inside their card
    Given the customer directory contains 23 test customers
    When the user navigates to the "Customers" view
    Then the "dirCustBody" table should show 10 rows with a pager summary starting "Showing 1–10 of"
    When the user moves to page "2" of the "dirCustBody" table
    Then the "dirCustBody" table should mark page "2" as current
    When the user searches the "dirCustBody" table for test customer "17"
    Then the "dirCustBody" table should show exactly 1 visible row containing test customer "17"

  Scenario: Submitting an invalid customer form shows inline field errors instead of saving
    When the user navigates to the "Customers" view
    And the user submits the customer form with an empty name and TRN "12345"
    Then the field "dirCustName" should show the inline error "Customer Name is required."
    And the field "dirCustTrn" should show the inline error "TRN must be exactly 15 digits (e.g. 100123456700003)."
    And no notification should be displayed
    When the user corrects the customer form with test name "Corrected Trading LLC" and TRN "100223344556603" and submits
    Then a "success" notification containing "saved successfully" should be displayed
    And the "dirCustBody" table should show a highlighted row containing "Corrected Trading LLC"

  Scenario: Deleting a customer asks for a styled confirmation that can be cancelled
    Given a test customer named "Delete Me Trading LLC" exists
    When the user navigates to the "Customers" view
    And the user clicks Delete for test customer "Delete Me Trading LLC"
    Then a danger confirmation dialog titled "Delete customer?" should mention "Delete Me Trading LLC"
    When the user cancels the confirmation dialog
    Then the "dirCustBody" table should still contain "Delete Me Trading LLC"
    When the user clicks Delete for test customer "Delete Me Trading LLC"
    And the user confirms the confirmation dialog
    Then a "info" notification containing "deleted" should be displayed
    And the "dirCustBody" table should not contain "Delete Me Trading LLC"

  Scenario: The General Ledger pages long histories instead of stretching the page
    Given the general ledger contains 25 test journal entries
    When the user navigates to the "General Ledger" view
    Then the "historyBody" table should show 10 rows with a pager summary starting "Showing 1–10 of"
    And the workspace should not need to scroll more than 1.5 screen heights

  @responsive
  Scenario: On a tablet-sized screen the sidebar becomes an off-canvas navigation drawer
    Given the browser window is resized to a 768 px wide tablet viewport
    Then the sidebar should be hidden off-canvas with the menu button reporting it collapsed
    When the user opens the navigation drawer
    Then the sidebar drawer should be visible above a backdrop
    When the user picks "Customers" from the navigation drawer
    Then the "view-customer-list" view should be displayed with the drawer closed
