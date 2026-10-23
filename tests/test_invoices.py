import unittest
from pathlib import Path

from hargasync.extraction import FIXTURE_PATH, FixtureExtractor
from tests.support import csrf, login, make_client, open_db

SAMPLE_PNG = FIXTURE_PATH.with_suffix(".png").read_bytes()


class InvoiceTestCase(unittest.TestCase):
    extractor = FixtureExtractor

    def setUp(self):
        self.client, self.settings = make_client(self, extractor=self.extractor())
        self.db = open_db(self, self.settings)

    def upload(self, data=SAMPLE_PNG, name="invoice.png"):
        return self.client.post(
            "/invoices",
            data={"csrf_token": csrf(self.client, "/")},
            files={"photo": (name, data, "image/png")},
            follow_redirects=False,
        )

    def product_id(self, sku, shop_id=1):
        return self.db.execute("SELECT id FROM products WHERE sku = ? AND shop_id = ?", (sku, shop_id)).fetchone()[0]

    def line(self, invoice_id, position):
        return self.db.execute(
            "SELECT * FROM invoice_lines WHERE invoice_id = ? AND position = ?", (invoice_id, position)
        ).fetchone()

    def count(self, table):
        return self.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    def lines_form(self, invoice_id, overrides=None, action="save"):
        """The review form as the browser would submit it, with per-position overrides."""
        overrides = overrides or {}
        rows = self.db.execute(
            "SELECT * FROM invoice_lines WHERE invoice_id = ? ORDER BY position", (invoice_id,)
        ).fetchall()
        form = {"csrf_token": csrf(self.client, f"/invoices/{invoice_id}"), "line_count": str(len(rows)), "action": action}
        for i, row in enumerate(rows, start=1):
            values = {
                "name": row["raw_name"], "unit": row["raw_unit"], "qty": row["qty"],
                "cost": f"{row['unit_cost_sen'] / 100:.2f}",
                "product": str(row["product_id"]) if row["match_status"] in ("matched", "confirmed") else "",
                "pack": str(row["pack_size"]),
            }
            values.update(overrides.get(row["position"], {}))
            for key, value in values.items():
                if value is not None:
                    form[f"{key}_{i}"] = value
        return form

    def save(self, invoice_id, overrides=None, action="save"):
        return self.client.post(
            f"/invoices/{invoice_id}/lines", data=self.lines_form(invoice_id, overrides, action), follow_redirects=False
        )


class TestUpload(InvoiceTestCase):
    def test_upload_reads_lines_and_matches_catalogue(self):
        login(self.client, "staff_mei")
        response = self.upload()
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/invoices/1")
        self.assertEqual(self.count("invoice_lines"), 8)
        gula = self.line(1, 1)
        self.assertEqual((gula["product_id"], gula["match_status"]), (self.product_id("GULA-1KG"), "matched"))
        self.assertEqual(self.line(1, 3)["match_status"], "uncertain")  # karton vs tin
        self.assertEqual(self.line(1, 7)["match_status"], "uncertain")  # typo
        self.assertEqual(self.line(1, 8)["match_status"], "unknown")
        page = self.client.get("/invoices/1")
        self.assertIn("Simulated AI", page.text)
        self.assertIn("Kicap Msin 340ml", page.text)

    def test_image_served_to_owning_shop(self):
        login(self.client, "staff_mei")
        self.upload()
        image = self.client.get("/invoices/1/image")
        self.assertEqual(image.status_code, 200)
        self.assertEqual(image.headers["content-type"], "image/png")

    def test_non_image_rejected_and_nothing_stored(self):
        login(self.client, "staff_mei")
        response = self.upload(data=b"not an image", name="notes.png")
        self.assertEqual(response.status_code, 400)
        self.assertIn("not a JPEG, PNG or WebP image", response.text)
        self.assertEqual(self.count("invoices"), 0)
        uploads = Path(self.settings.data_dir) / "uploads"
        self.assertEqual(list(uploads.rglob("*")) if uploads.exists() else [], [])

    def test_oversize_rejected(self):
        login(self.client, "staff_mei")
        response = self.upload(data=SAMPLE_PNG + b"\0" * (9 * 1024 * 1024))
        self.assertEqual(response.status_code, 400)
        self.assertIn("8 MB", response.text)
        self.assertEqual(self.count("invoices"), 0)

    def test_auditor_cannot_upload(self):
        login(self.client, "auditor_raj")
        self.assertEqual(self.upload().status_code, 403)

    def test_other_shop_gets_404(self):
        login(self.client, "owner_ali")
        self.upload()
        login(self.client, "owner_siti")
        self.assertEqual(self.client.get("/invoices/1").status_code, 404)
        self.assertEqual(self.client.get("/invoices/1/image").status_code, 404)
        response = self.client.post("/invoices/1/confirm", data={"csrf_token": csrf(self.client, "/")})
        self.assertEqual(response.status_code, 404)

    def test_manual_invoice_without_photo(self):
        login(self.client, "staff_mei")
        response = self.client.post(
            "/invoices", data={"csrf_token": csrf(self.client, "/"), "manual": "1"}, follow_redirects=False
        )
        self.assertEqual(response.status_code, 303)
        invoice = self.db.execute("SELECT * FROM invoices").fetchone()
        self.assertEqual((invoice["status"], invoice["extraction_source"]), ("manual", "manual"))
        form = {
            "csrf_token": csrf(self.client, "/invoices/1"), "line_count": "0", "action": "save",
            "name_1": "Gula Pasir Kasar 1kg", "unit_1": "pek", "qty_1": "10", "cost_1": "2.80",
            "product_1": "", "pack_1": "1",
        }
        self.client.post("/invoices/1/lines", data=form)
        line = self.line(1, 1)
        self.assertEqual((line["product_id"], line["match_status"], line["unit_cost_sen"]), (self.product_id("GULA-1KG"), "matched", 280))


class TestFailedExtraction(InvoiceTestCase):
    extractor = None  # make_client falls back to DisabledExtractor

    def setUp(self):
        self.client, self.settings = make_client(self)
        self.db = open_db(self, self.settings)

    def test_failed_reading_opens_manual_entry(self):
        login(self.client, "staff_mei")
        self.assertEqual(self.upload().status_code, 303)
        invoice = self.db.execute("SELECT * FROM invoices").fetchone()
        self.assertEqual(invoice["status"], "manual")
        self.assertIn("not configured", invoice["extraction_error"])
        self.assertEqual(self.count("invoice_lines"), 0)
        page = self.client.get("/invoices/1")
        self.assertIn("Type the lines from the photo", page.text)


class TestReviewAndConfirm(InvoiceTestCase):
    def setUp(self):
        super().setUp()
        login(self.client, "staff_mei")
        self.upload()

    def resolve_all(self, action="save"):
        return self.save(1, {
            3: {"product": str(self.product_id("SUSU-500G")), "pack": "24"},
            7: {"product": str(self.product_id("KICAP-340"))},
            8: {"skip": "1"},
        }, action=action)

    def test_confirm_with_unresolved_lines_refused(self):
        response = self.client.post("/invoices/1/confirm", data={"csrf_token": csrf(self.client, "/invoices/1")})
        self.assertEqual(response.status_code, 200)
        self.assertIn("Resolve 3 lines", response.text)
        self.assertEqual(self.count("price_proposals"), 0)

    def test_duplicate_product_refused(self):
        gula = str(self.product_id("GULA-1KG"))
        overrides = {p: {"skip": "1"} for p in range(3, 9)}
        overrides[2] = {"product": gula}
        self.save(1, overrides)
        response = self.client.post("/invoices/1/confirm", data={"csrf_token": csrf(self.client, "/invoices/1")})
        self.assertIn("duplicate product", response.text)
        self.assertEqual(self.count("price_proposals"), 0)

    def test_bad_cost_rejected_with_message(self):
        response = self.save(1, {1: {"cost": "12,50"}})
        self.assertEqual(response.status_code, 303)
        page = self.client.get("/invoices/1")
        self.assertIn("12,50", page.text)
        self.assertEqual(self.line(1, 1)["unit_cost_sen"], 275)

    def test_confirm_creates_proposals_and_learns_alias(self):
        response = self.resolve_all(action="confirm")
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/proposals")
        self.assertEqual(self.count("price_proposals"), 7)
        susu = self.db.execute(
            "SELECT * FROM price_proposals WHERE product_id = ?", (self.product_id("SUSU-500G"),)
        ).fetchone()
        self.assertEqual(susu["new_cost_sen"], 330)  # RM 79.20 per karton of 24
        alias = self.db.execute("SELECT * FROM product_aliases WHERE unit_norm = 'karton'").fetchone()
        self.assertEqual((alias["product_id"], alias["pack_size"]), (self.product_id("SUSU-500G"), 24))
        ayam = self.db.execute(
            "SELECT * FROM price_proposals WHERE product_id = ?", (self.product_id("AYAM-KG"),)
        ).fetchone()
        self.assertEqual((ayam["proposed_price_sen"], ayam["cap_sen"], ayam["required_role"]), (940, 940, "owner"))
        telur = self.db.execute(
            "SELECT * FROM price_proposals WHERE product_id = ?", (self.product_id("TELUR-A30"),)
        ).fetchone()
        self.assertEqual(telur["status"], "blocked")
        invoice = self.db.execute("SELECT status FROM invoices WHERE id = 1").fetchone()
        self.assertEqual(invoice["status"], "proposed")

    def test_next_invoice_matches_learned_alias(self):
        self.resolve_all(action="confirm")
        self.upload()
        self.assertEqual((self.line(2, 3)["match_status"], self.line(2, 3)["pack_size"]), ("matched", 24))

    def test_proposed_invoice_cannot_be_edited(self):
        self.resolve_all(action="confirm")
        self.resolve_all()
        page = self.client.get("/invoices/1")
        self.assertIn("already has price proposals", page.text)


if __name__ == "__main__":
    unittest.main()
