"""Page Object for Customers, Suppliers, Inventory Directory, Stock Ledger, and Cheque Registry."""

from __future__ import annotations

from features.pages.base_page import BasePage


class ContactsAndInventoryPage(BasePage):
    """UI adapter for `#view-customer-list`, `#view-supplier-list`, `#view-inventory`, `#view-stock-ledger`, and `#view-cheques`."""

    # --- Customers (`#view-customer-list`) ---

    def add_customer(
        self,
        name: str,
        address: str,
        phone: str,
        email: str,
        trn: str,
        payment_terms: str,
    ) -> None:
        """Populate and submit `#addCustomerForm`."""
        self.fill_input("dirCustName", name)
        self.fill_input("dirCustAddress", address)
        self.fill_input("dirCustPhone", phone)
        self.fill_input("dirCustEmail", email)
        self.fill_input("dirCustTrn", trn)
        self.fill_input("dirCustTerms", payment_terms)
        self.evaluate_script(
            "document.getElementById('addCustomerForm').requestSubmit();"
        )
        self.accept_alert_if_present(timeout=1.5)

    def get_customer_directory_text(self) -> str:
        """Return the text of `#dirCustBody`."""
        return self.get_text_by_id("dirCustBody")

    # --- Suppliers (`#view-supplier-list`) ---

    def add_supplier(
        self,
        name: str,
        trn: str,
        address: str,
        phone: str,
        payment_terms: str,
    ) -> None:
        """Populate and submit `#addSupplierForm`."""
        self.fill_input("dirSupName", name)
        self.fill_input("dirSupTrn", trn)
        self.fill_input("dirSupAddress", address)
        self.fill_input("dirSupPhone", phone)
        self.fill_input("dirSupTerms", payment_terms)
        self.evaluate_script(
            "document.getElementById('addSupplierForm').requestSubmit();"
        )
        self.accept_alert_if_present(timeout=1.5)

    def get_supplier_directory_text(self) -> str:
        """Return the text of `#dirSupBody`."""
        return self.get_text_by_id("dirSupBody")

    # --- Inventory Directory (`#view-inventory`) ---

    def set_inventory_cost_and_markup(self, unit_cost: str, markup_pct: str) -> str:
        """Enter unit cost and markup percentage and return the auto-calculated selling price."""
        self.fill_input("invCost", unit_cost)
        self.fill_input("invMarkup", markup_pct)
        return self.get_value_by_id("invPrice")

    def add_inventory_item(
        self,
        name: str,
        sku: str,
        description: str,
        unit_cost: str,
        markup_pct: str,
        initial_qty: str,
    ) -> None:
        """Populate and submit `#addInventoryForm`."""
        self.fill_input("invName", name)
        self.fill_input("invSku", sku)
        self.fill_input("invDesc", description)
        self.fill_input("invCost", unit_cost)
        self.fill_input("invMarkup", markup_pct)
        self.fill_input("invQty", initial_qty)
        self.evaluate_script(
            "document.getElementById('addInventoryForm').requestSubmit();"
        )
        self.accept_alert_if_present(timeout=1.5)

    def get_inventory_directory_text(self) -> str:
        """Return the text of `#inventoryDirectoryBody`."""
        return self.get_text_by_id("inventoryDirectoryBody")

    # --- Stock Ledger (`#view-stock-ledger`) ---

    def get_stock_ledger_text(self) -> str:
        """Return the text of `#stockLedgerBody`."""
        return self.get_text_by_id("stockLedgerBody")

    # --- Cheque Registry (`#view-cheques`) ---

    def register_cheque(
        self,
        cheque_number: str,
        created_date: str,
        cheque_date: str,
        amount: str,
        supplier_name: str,
        bank_account: str,
    ) -> None:
        """Populate and submit `#addChequeForm`."""
        self.fill_input("chequeNumber", cheque_number)
        self.fill_input("chequeCreatedDate", created_date)
        self.fill_input("chequeDate", cheque_date)
        self.fill_input("chequeAmount", amount)
        self.fill_input("chequeSupplier", supplier_name)
        self.fill_input("chequeBank", bank_account)
        self.evaluate_script(
            "document.getElementById('addChequeForm').requestSubmit();"
        )
        self.accept_alert_if_present(timeout=1.5)

    def get_cheque_registry_text(self) -> str:
        """Return the text of `#chequeRegistryBody`."""
        return self.get_text_by_id("chequeRegistryBody")
