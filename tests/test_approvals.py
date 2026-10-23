import unittest

from tests.support import csrf, login
from tests.test_invoices import InvoiceTestCase


class ApprovalTestCase(InvoiceTestCase):
    """Staff uploads the sample invoice and creates its 7 proposals; tests then log in as needed."""

    def setUp(self):
        super().setUp()
        login(self.client, "staff_mei")
        self.upload()
        self.resolve(1)

    def resolve(self, invoice_id):
        self.save(invoice_id, {
            3: {"product": str(self.product_id("SUSU-500G")), "pack": "24"},
            7: {"product": str(self.product_id("KICAP-340"))},
            8: {"skip": "1"},
        }, action="confirm")

    def proposal(self, sku, invoice_id=1):
        return self.db.execute(
            "SELECT * FROM price_proposals WHERE product_id = ? AND invoice_id = ?",
            (self.product_id(sku), invoice_id),
        ).fetchone()

    def product(self, sku):
        return self.db.execute("SELECT * FROM products WHERE id = ?", (self.product_id(sku),)).fetchone()

    def events(self, event_type):
        return self.db.execute("SELECT COUNT(*) FROM audit_events WHERE event_type = ?", (event_type,)).fetchone()[0]

    def approve(self, sku, override="", note="", invoice_id=1, follow=True):
        proposal_id = self.proposal(sku, invoice_id)["id"]
        return self.client.post(
            f"/proposals/{proposal_id}/approve",
            data={"csrf_token": csrf(self.client, "/proposals"), "override_price": override, "note": note},
            follow_redirects=follow,
        )


class TestStaffApproval(ApprovalTestCase):
    def test_staff_approves_eligible_change(self):
        self.assertEqual(self.proposal("SUSU-500G")["required_role"], "staff")
        response = self.approve("SUSU-500G")
        self.assertEqual(response.status_code, 200)
        product = self.product("SUSU-500G")
        self.assertEqual((product["price_sen"], product["cost_sen"], product["version"]), (390, 330, 2))
        proposal = self.proposal("SUSU-500G")
        self.assertEqual((proposal["status"], proposal["final_price_sen"]), ("approved", 390))
        self.assertEqual(self.events("price_approved"), 1)

    def test_staff_blocked_from_owner_only_change(self):
        response = self.approve("MINYAK-5KG")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.product("MINYAK-5KG")["price_sen"], 3200)
        self.assertEqual(self.proposal("MINYAK-5KG")["status"], "pending")

    def test_staff_cannot_override(self):
        response = self.approve("SUSU-500G", override="3.80", note="keep old price")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.product("SUSU-500G")["version"], 1)

    def test_auditor_cannot_approve(self):
        login(self.client, "auditor_raj")
        self.assertEqual(self.approve("SUSU-500G").status_code, 403)


class TestOwnerApproval(ApprovalTestCase):
    def setUp(self):
        super().setUp()
        login(self.client, "owner_ali")

    def test_override_above_cap_refused(self):
        response = self.approve("AYAM-KG", override="9.50", note="supplier up")
        self.assertIn("above the ceiling", response.text)
        self.assertEqual(self.product("AYAM-KG")["price_sen"], 920)

    def test_override_needs_reason(self):
        response = self.approve("AYAM-KG", override="9.30")
        self.assertIn("reason", response.text)
        self.assertEqual(self.product("AYAM-KG")["version"], 1)

    def test_override_with_reason_applies(self):
        self.approve("AYAM-KG", override="9.30", note="match the pasar price")
        self.assertEqual(self.product("AYAM-KG")["price_sen"], 930)
        self.assertEqual(self.proposal("AYAM-KG")["decision_note"], "match the pasar price")

    def test_owner_approves_capped_price(self):
        self.approve("AYAM-KG")
        self.assertEqual(self.product("AYAM-KG")["price_sen"], 940)

    def test_second_approval_writes_nothing(self):
        self.approve("MINYAK-5KG")
        response = self.approve("MINYAK-5KG")
        self.assertIn("already approved", response.text)
        self.assertEqual(self.product("MINYAK-5KG")["version"], 2)
        self.assertEqual(self.events("price_approved"), 1)

    def test_blocked_proposal_cannot_be_approved(self):
        response = self.approve("TELUR-A30")
        self.assertIn("No valid ceiling", response.text)
        self.assertEqual(self.product("TELUR-A30")["price_sen"], 1450)

    def test_stale_proposal_refused(self):
        self.upload()
        self.resolve(2)  # learned aliases: all lines match; biscuits still skipped
        self.approve("SUSU-500G", invoice_id=1)
        response = self.approve("SUSU-500G", invoice_id=2)
        self.assertIn("catalogue changed", response.text)
        self.assertEqual(self.proposal("SUSU-500G", invoice_id=2)["status"], "stale")
        self.assertEqual(self.product("SUSU-500G")["version"], 2)

    def test_reject_leaves_price(self):
        proposal_id = self.proposal("MINYAK-5KG")["id"]
        self.client.post(
            f"/proposals/{proposal_id}/reject",
            data={"csrf_token": csrf(self.client, "/proposals"), "note": "wrong supplier price"},
        )
        self.assertEqual(self.proposal("MINYAK-5KG")["status"], "rejected")
        self.assertEqual(self.product("MINYAK-5KG")["price_sen"], 3200)
        self.assertEqual(self.events("price_rejected"), 1)

    def test_other_shop_owner_gets_404(self):
        login(self.client, "owner_siti")
        self.assertEqual(self.approve("SUSU-500G").status_code, 404)
        self.assertEqual(self.product("SUSU-500G")["version"], 1)

    def test_proposals_page_labels_demo_ceiling(self):
        page = self.client.get("/proposals")
        self.assertEqual(page.status_code, 200)
        self.assertIn("DEMO — fictional ceiling", page.text)
        self.assertIn("Ayam Standard (sekilo)", page.text)
        self.assertIn("RM 9.40", page.text)


if __name__ == "__main__":
    unittest.main()
