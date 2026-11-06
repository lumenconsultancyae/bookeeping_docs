"""Unit & component tests for the bookkeeping-tool feedback and inline-validation layer.

User stories covered:
1. As a bookkeeper I never see blocking native browser dialogs; every module uses the
   design-system toasts and dialogs (`ui-feedback.js`) instead of alert/confirm/prompt.
2. As a bookkeeper deleting a record I get a clear, styled, keyboard-accessible confirmation.
3. As a bookkeeper filling a form I see inline, specific errors next to the invalid field
   instead of a browser tooltip, and the save handler only runs once the form is valid (`ui-forms.js`).
"""

from __future__ import annotations

from pathlib import Path
import re
import unittest

from tests.dom_harness import APP_DIR, DomComponentHarness

NATIVE_DIALOG_CALL = re.compile(r"(?<![\w.$])(?:window\.)?(alert|confirm|prompt)\s*\(")
LUMEN_CALL = re.compile(r"LumenUI\.(confirm|prompt)\s*\(")


def _app_sources() -> dict[str, str]:
    files = sorted(APP_DIR.glob("*.js")) + sorted(APP_DIR.glob("*.html"))
    return {p.name: p.read_text(encoding="utf-8") for p in files}


class NativeDialogEliminationTests(unittest.TestCase):
    """Static guardrails: no native dialogs anywhere in the shipped front-end."""

    def test_no_module_or_template_calls_native_alert_confirm_or_prompt(self) -> None:
        offenders: list[str] = []
        for name, src in _app_sources().items():
            for lineno, line in enumerate(src.splitlines(), start=1):
                stripped = LUMEN_CALL.sub("", line)
                if NATIVE_DIALOG_CALL.search(stripped) and not stripped.lstrip().startswith(("//", "*")):
                    offenders.append(f"{name}:{lineno}: {line.strip()[:120]}")
        self.assertEqual(offenders, [], "Native dialogs found:\n" + "\n".join(offenders))

    def test_index_loads_feedback_before_features_and_enhancers_after(self) -> None:
        html = (APP_DIR / "index.html").read_text(encoding="utf-8")
        pos = {name: html.index(f'src="{name}') for name in (
            "ui-feedback.js", "views-transactions.js", "profiles-ui.js", "app-core-and-router.js",
            "script.js", "i18n.js", "ui-forms.js", "ui-tables.js", "ui-layout.js")}
        self.assertLess(pos["ui-feedback.js"], pos["views-transactions.js"])
        self.assertLess(pos["ui-feedback.js"], pos["profiles-ui.js"])
        for enhancer in ("ui-forms.js", "ui-tables.js", "ui-layout.js"):
            self.assertGreater(pos[enhancer], pos["script.js"])
            self.assertGreater(pos[enhancer], pos["i18n.js"])
        self.assertGreater(html.index('href="ui-kit.css'), html.index('href="theme-pro.css'))

    def test_legacy_toast_and_modal_implementations_delegate_to_shared_layer(self) -> None:
        profiles_ui = (APP_DIR / "profiles-ui.js").read_text(encoding="utf-8")
        expenses = (APP_DIR / "expenses.js").read_text(encoding="utf-8")
        self.assertNotIn("profile-modal-overlay", profiles_ui)
        self.assertNotIn("profile-toast", profiles_ui)
        self.assertIn("window.LumenUI.toast", profiles_ui)
        self.assertNotIn("exp-toast", expenses)
        self.assertIn("window.LumenUI.toast", expenses)
        self.assertIn("Object.assign(window.LumenUI || {}", profiles_ui)


class FeedbackLayerComponentTests(unittest.TestCase):
    """`ui-feedback.js` toasts, confirm and prompt dialogs in a real DOM."""

    def setUp(self) -> None:
        self.dom = DomComponentHarness()
        self.dom.mount('<button id="opener">Delete</button>', modules=("ui-feedback.js",))

    def test_toasts_use_semantic_types_roles_dedupe_and_cap_the_stack(self) -> None:
        result = self.dom.run("""
            const { toast } = window.LumenUI;
            toast('Customer "Acme" saved.', 'success');
            toast('Cannot delete: This entry is in a closed month.');
            toast('Customer "Acme" deleted.', 'info');
            toast('Customer "Acme" deleted.', 'info');
            await tick(260);
            const els = Array.from(document.querySelectorAll('#lumenToastRegion .lumen-toast:not([data-leaving])'));
            for (let i = 0; i < 6; i++) toast('Bulk ' + i, 'info');
            done({
                kinds: els.map((e) => e.className.match(/lumen-toast--(\\w+)/)[1]),
                roles: els.map((e) => e.getAttribute('role')),
                live: document.getElementById('lumenToastRegion').getAttribute('aria-live'),
                capped: document.querySelectorAll('#lumenToastRegion .lumen-toast').length,
                closeLabel: els[0].querySelector('.lumen-toast__close').getAttribute('aria-label'),
            });
        """)
        self.assertEqual(result["kinds"], ["success", "error", "info"])
        self.assertEqual(result["roles"], ["status", "alert", "status"])
        self.assertEqual(result["live"], "polite")
        self.assertLessEqual(result["capped"], 4)
        self.assertEqual(result["closeLabel"], "Dismiss notification")

    def test_toast_close_button_dismisses_and_message_is_escaped(self) -> None:
        result = self.dom.run("""
            const el = window.LumenUI.toast('<img src=x onerror=alert(1)>', 'warning');
            const injected = el.querySelector('img') !== null;
            el.querySelector('.lumen-toast__close').click();
            await tick(300);
            done({ injected, remaining: document.querySelectorAll('.lumen-toast').length });
        """)
        self.assertFalse(result["injected"])
        self.assertEqual(result["remaining"], 0)

    def test_danger_confirm_resolves_true_on_confirm_and_restores_focus(self) -> None:
        result = self.dom.run("""
            document.getElementById('opener').focus();
            const pending = window.LumenUI.confirm({ title: 'Delete customer?', message: '"Acme" will be removed.',
                confirmText: 'Delete customer', danger: true });
            await tick(30);
            const dialog = document.querySelector('.lumen-dialog');
            const info = {
                role: dialog.getAttribute('role'), modal: dialog.getAttribute('aria-modal'),
                danger: dialog.classList.contains('lumen-dialog--danger'),
                labelled: document.getElementById(dialog.getAttribute('aria-labelledby')).textContent,
                described: document.getElementById(dialog.getAttribute('aria-describedby')).textContent,
                focusedCancel: document.activeElement.dataset.dialogAction,
                confirmLabel: dialog.querySelector('[data-dialog-action="confirm"]').textContent,
            };
            dialog.querySelector('[data-dialog-action="confirm"]').click();
            info.result = await pending;
            info.closed = !document.querySelector('.lumen-dialog-backdrop');
            info.focusRestored = document.activeElement.id;
            done(info);
        """)
        self.assertEqual(result["role"], "alertdialog")
        self.assertEqual(result["modal"], "true")
        self.assertTrue(result["danger"])
        self.assertEqual(result["labelled"], "Delete customer?")
        self.assertIn("Acme", result["described"])
        self.assertEqual(result["focusedCancel"], "cancel", "Destructive dialogs focus the safe action first")
        self.assertEqual(result["confirmLabel"], "Delete customer")
        self.assertIs(result["result"], True)
        self.assertTrue(result["closed"])
        self.assertEqual(result["focusRestored"], "opener")

    def test_confirm_resolves_false_on_escape_cancel_and_backdrop(self) -> None:
        result = self.dom.run("""
            const outcomes = [];
            let p = window.LumenUI.confirm({ title: 'Convert quote?' });
            await tick(20);
            document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
            outcomes.push(await p);
            p = window.LumenUI.confirm('Proceed?');
            await tick(20);
            document.querySelector('[data-dialog-action="cancel"]').click();
            outcomes.push(await p);
            p = window.LumenUI.confirm('Proceed?');
            await tick(20);
            const backdrop = document.querySelector('.lumen-dialog-backdrop');
            backdrop.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
            outcomes.push(await p);
            done({ outcomes, bodyLocked: document.body.classList.contains('has-lumen-dialog') });
        """)
        self.assertEqual(result["outcomes"], [False, False, False])
        self.assertFalse(result["bodyLocked"])

    def test_tab_key_is_trapped_inside_the_dialog(self) -> None:
        result = self.dom.run("""
            const p = window.LumenUI.confirm({ title: 'Lock ledger?' });
            await tick(20);
            const [cancel, confirm] = document.querySelectorAll('.lumen-dialog button');
            confirm.focus();
            document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true }));
            const afterTab = document.activeElement === cancel;
            document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', shiftKey: true, bubbles: true, cancelable: true }));
            const afterShiftTab = document.activeElement === confirm;
            confirm.click();
            await p;
            done({ afterTab, afterShiftTab });
        """)
        self.assertTrue(result["afterTab"])
        self.assertTrue(result["afterShiftTab"])

    def test_prompt_validates_inline_before_resolving_and_null_on_cancel(self) -> None:
        result = self.dom.run("""
            const p = window.LumenUI.prompt({ title: 'Depreciation period', label: 'Useful life (years)',
                type: 'number', min: 1, step: 1, value: '' });
            await tick(20);
            const input = document.querySelector('.lumen-dialog input');
            const confirm = document.querySelector('[data-dialog-action="confirm"]');
            confirm.click();
            const requiredError = document.querySelector('.lumen-dialog .field-error').textContent;
            input.value = '0';
            confirm.click();
            const minError = document.querySelector('.lumen-dialog .field-error').textContent;
            const invalidFlag = input.getAttribute('aria-invalid');
            input.value = '5';
            input.dispatchEvent(new Event('input', { bubbles: true }));
            confirm.click();
            const value = await p;
            const p2 = window.LumenUI.prompt({ title: 'Period', label: 'Months', type: 'number', min: 1 });
            await tick(20);
            document.querySelector('[data-dialog-action="cancel"]').click();
            done({ requiredError, minError, invalidFlag, value, cancelled: await p2 });
        """)
        self.assertEqual(result["requiredError"], "Useful life (years) is required.")
        self.assertTrue(result["minError"])
        self.assertEqual(result["invalidFlag"], "true")
        self.assertEqual(result["value"], "5")
        self.assertIsNone(result["cancelled"])

    def test_legacy_open_modal_contract_returns_true_null_or_value(self) -> None:
        result = self.dom.run("""
            const p1 = window.LumenUI.openModal({ title: 'Upgrade?', confirmText: 'Upgrade' });
            await tick(20);
            document.querySelector('[data-dialog-action="confirm"]').click();
            const p2 = window.LumenUI.openModal({ title: 'Delete?', confirmText: 'Delete', danger: true });
            await tick(20);
            document.querySelector('[data-dialog-action="cancel"]').click();
            const p3 = window.LumenUI.openModal({ title: 'Rename', inputValue: 'Old Co', confirmText: 'Save' });
            await tick(20);
            document.querySelector('.lumen-dialog input').value = '  New Co  ';
            document.querySelector('[data-dialog-action="confirm"]').click();
            done([await p1, await p2, await p3]);
        """)
        self.assertEqual(result, [True, None, "New Co"])


FORM_FIXTURE = """
<form id="addCustomerForm" class="form-grid">
  <div class="form-group"><label>Customer Name</label><input type="text" id="dirCustName" required></div>
  <div class="form-group"><label>Email Address</label><input type="email" id="dirCustEmail"></div>
  <div class="form-group"><label>VAT TRN</label><input type="text" id="dirCustTrn" pattern="[0-9]{15}"
       data-error-pattern="TRN must be exactly 15 digits (e.g. 100123456700003)."></div>
  <div class="form-group"><label>Amount</label><input type="number" id="amt" min="0.01" step="0.01"
       data-error-min="Amount must be greater than zero."></div>
  <div class="form-group"><label>Account</label><select id="acct" required><option value="">Select…</option><option>4000</option></select></div>
  <button type="submit" id="save">Save Customer</button>
</form>
<div id="poEditor"><div class="form-group"><label>PO Number</label><input id="poNum"></div>
  <div class="form-group"><label>Supplier</label><input id="poSupp"></div></div>
"""


class InlineFormValidationComponentTests(unittest.TestCase):
    """`ui-forms.js` replaces native validation bubbles with accessible inline errors."""

    def setUp(self) -> None:
        self.dom = DomComponentHarness()
        self.dom.mount(FORM_FIXTURE, modules=("ui-feedback.js", "ui-forms.js"))
        self.dom.run("""
            window.__saved = 0;
            document.getElementById('addCustomerForm').addEventListener('submit', (e) => { e.preventDefault(); window.__saved++; });
            done(true);
        """)

    def test_invalid_submit_renders_inline_errors_focuses_first_field_and_blocks_save(self) -> None:
        result = self.dom.run("""
            document.getElementById('dirCustEmail').value = 'not-an-email';
            document.getElementById('dirCustTrn').value = '12345';
            document.getElementById('amt').value = '0';
            document.getElementById('save').click();
            await tick(30);
            const err = (id) => { const el = document.getElementById(id + '-error'); return el && !el.hidden ? el.textContent : null; };
            const name = document.getElementById('dirCustName');
            done({
                saved: window.__saved, name: err('dirCustName'), email: err('dirCustEmail'), trn: err('dirCustTrn'),
                amt: err('amt'), acct: err('acct'), focused: document.activeElement.id,
                invalid: name.getAttribute('aria-invalid'), describedBy: name.getAttribute('aria-describedby'),
                groupFlag: name.closest('.form-group').classList.contains('has-error'),
            });
        """)
        self.assertEqual(result["saved"], 0)
        self.assertEqual(result["name"], "Customer Name is required.")
        self.assertIn("valid email", result["email"])
        self.assertEqual(result["trn"], "TRN must be exactly 15 digits (e.g. 100123456700003).")
        self.assertEqual(result["amt"], "Amount must be greater than zero.")
        self.assertEqual(result["acct"], "Select account.")
        self.assertEqual(result["focused"], "dirCustName")
        self.assertEqual(result["invalid"], "true")
        self.assertIn("dirCustName-error", result["describedBy"])
        self.assertTrue(result["groupFlag"])

    def test_errors_clear_live_and_valid_submit_reaches_the_save_handler(self) -> None:
        result = self.dom.run("""
            document.getElementById('save').click();
            await tick(20);
            const name = document.getElementById('dirCustName');
            name.value = 'Oasis Digital Media LLC';
            name.dispatchEvent(new Event('input', { bubbles: true }));
            const clearedLive = document.getElementById('dirCustName-error').hidden && !name.hasAttribute('aria-invalid');
            const acct = document.getElementById('acct');
            acct.value = '4000';
            acct.dispatchEvent(new Event('change', { bubbles: true }));
            document.getElementById('dirCustTrn').value = '100223344556603';
            document.getElementById('save').click();
            await tick(20);
            done({ clearedLive, saved: window.__saved });
        """)
        self.assertTrue(result["clearedLive"])
        self.assertEqual(result["saved"], 1)

    def test_required_labels_are_marked_and_reset_clears_errors(self) -> None:
        result = self.dom.run("""
            const required = Array.from(document.querySelectorAll('label.is-required')).map((l) => l.textContent);
            document.getElementById('save').click();
            await tick(20);
            document.getElementById('addCustomerForm').reset();
            await tick(20);
            done({ required, flagged: document.querySelectorAll('[aria-invalid="true"]').length });
        """)
        self.assertEqual(result["required"], ["Customer Name", "Account"])
        self.assertEqual(result["flagged"], 0)

    def test_validate_fields_supports_non_form_editors_with_custom_tests(self) -> None:
        result = self.dom.run("""
            const ok1 = window.LumenUI.validateFields([
                { field: 'poNum', message: 'Enter a PO number.' },
                { field: document.getElementById('poSupp'), message: 'Select a supplier.' },
            ]);
            const first = { num: document.getElementById('poNum-error').textContent, focused: document.activeElement.id };
            document.getElementById('poNum').value = 'PO-1001';
            document.getElementById('poSupp').value = 'x';
            const ok2 = window.LumenUI.validateFields([
                { field: 'poNum' },
                { field: 'poSupp', message: 'Supplier name is too short.', test: (v) => v.length > 2 },
            ]);
            done({ ok1, ok2, first, numCleared: document.getElementById('poNum-error').hidden,
                   supp: document.getElementById('poSupp-error').textContent });
        """)
        self.assertFalse(result["ok1"])
        self.assertEqual(result["first"], {"num": "Enter a PO number.", "focused": "poNum"})
        self.assertFalse(result["ok2"])
        self.assertTrue(result["numCleared"])
        self.assertEqual(result["supp"], "Supplier name is too short.")


if __name__ == "__main__":
    unittest.main()
