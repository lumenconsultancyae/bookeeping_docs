@contacts @inventory
Feature: Customer, Supplier, Inventory, Stock Ledger, and Cheque Directories
  As an operations manager using Lumen Accounting Suite
  I want to maintain customer and supplier records, track inventory items and stock movements, and register cheques
  So that master data and stock valuations stay synchronized with commercial operations

  Background:
    Given the bookkeeping application is open on the "Dashboard" view

  @smoke
  Scenario Outline: Registering a new contact in the Customer or Supplier directory
    When the user navigates to the "<directory_view>" view
    And the user registers a "<contact_type>" named "<entity_name>" with TRN "<trn>" and payment terms "<terms>" days
    Then the "<directory_view>" directory should list the contact "<entity_name>" with TRN "<trn>"

    Examples:
      | directory_view | contact_type | entity_name              | trn             | terms |
      | Customers      | customer     | Oasis Digital Media LLC  | 100223344556603 | 30    |
      | Suppliers      | supplier     | Emirates Paper Mills LLC | 100778899001103 | 45    |

  Scenario: Adding an inventory item calculates markup selling price and records an opening Stock Ledger movement
    When the user navigates to the "Inventory Directory" view
    And the user enters an inventory unit cost of "200.00" AED and a markup of "35" percent
    Then the calculated selling price field should be "270.00"
    When the user saves the inventory item "Enterprise Wi-Fi 7 Access Point" with SKU "AP-WIFI7" and initial quantity "15"
    Then the Inventory Directory should list "Enterprise Wi-Fi 7 Access Point" with quantity "15"
    When the user navigates to the "Stock Ledger" view
    Then the Stock Ledger should record an "Initial Stock" movement for "Enterprise Wi-Fi 7 Access Point" of "+15"

  Scenario: Registering a supplier payment cheque in the Cheque Registry
    When the user navigates to the "Cheque Registry" view
    And the user registers cheque "CHQ-7701" for "3250.00" AED payable to "Al Futtaim Logistics" from "1100 Bank Account"
    Then the Cheque Registry should list cheque "CHQ-7701" for supplier "Al Futtaim Logistics"
