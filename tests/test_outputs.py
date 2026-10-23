import unittest

from tests.support import csrf, login
from tests.test_approvals import ApprovalTestCase


class TestTags(ApprovalTestCase):
    def setUp(self):
        super().setUp()
        login(self.client, "owner_ali")
        self.approve("AYAM-KG")
        self.approve("SUSU-500G")

    def test_tag_shows_approved_price_in_bm(self):
        page = self.client.get(f"/tags/print?ids={self.product_id('AYAM-KG')}")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Ayam Standard (sekilo)", page.text)
        self.assertIn("RM 9.40", page.text)
        self.assertIn("Harga berkuat kuasa", page.text)
        self.assertIn("Barang kawalan harga", page.text)
        self.assertIn("DEMO — fictional ceiling", page.text)

    def test_tag_price_matches_catalogue(self):
        page = self.client.get(f"/tags/print?ids={self.product_id('SUSU-500G')}")
        self.assertIn("RM 3.90", page.text)
        self.assertNotIn("RM 3.80", page.text)

    def test_other_shop_ids_ignored(self):
        roti = self.product_id("ROTI-400G", shop_id=2)
        page = self.client.get(f"/tags/print?ids={roti}")
        self.assertNotIn("Roti Putih", page.text)

    def test_recent_approvals_preselected(self):
        page = self.client.get("/tags")
        self.assertRegex(page.text, rf'value="{self.product_id("AYAM-KG")}"\s+checked')
        self.assertNotRegex(page.text, rf'value="{self.product_id("BERAS-5KG")}"\s+checked')


class TestActivityAndCatalogue(ApprovalTestCase):
    def test_auditor_sees_activity(self):
        login(self.client, "owner_ali")
        self.approve("AYAM-KG")
        login(self.client, "auditor_raj")
        page = self.client.get("/activity")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Price approved", page.text)
        self.assertIn("Ali bin Hassan", page.text)
        self.assertIn("RM 9.40", page.text)

    def add_product(self, **overrides):
        form = {
            "csrf_token": csrf(self.client, "/catalogue"), "sku": "BISKUT-400G", "name_bm": "Biskut Kraker Krim 400g",
            "unit": "pek", "cost": "4.20", "price": "", "margin": "18", "controlled_item_code": "",
        }
        form.update(overrides)
        return self.client.post("/catalogue", data=form)

    def test_staff_cannot_add_product(self):
        self.assertEqual(self.add_product().status_code, 403)

    def test_owner_adds_product(self):
        login(self.client, "owner_ali")
        page = self.add_product()
        self.assertEqual(page.status_code, 200)
        self.assertIn("Biskut Kraker Krim 400g", self.client.get("/catalogue").text)
        product = self.db.execute("SELECT * FROM products WHERE sku = 'BISKUT-400G'").fetchone()
        self.assertEqual((product["shop_id"], product["cost_sen"], product["price_sen"], product["target_margin"]), (1, 420, None, "0.18"))

    def test_duplicate_sku_refused(self):
        login(self.client, "owner_ali")
        page = self.add_product(sku="GULA-1KG")
        self.assertIn("already used", page.text)

    def test_unpriced_product_skipped_on_tags(self):
        login(self.client, "owner_ali")
        self.add_product()
        page = self.client.get(f"/tags/print?ids={self.product_id('BISKUT-400G')}")
        self.assertIn("no approved price yet", page.text)


if __name__ == "__main__":
    unittest.main()
