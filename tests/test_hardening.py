"""Regression tests for the whole-branch review findings."""

import os
import threading
import time
import unittest
from unittest import mock

import httpx

from hargasync import invoices as invoices_module
from hargasync.auth import load_user
from hargasync.config import load_settings
from hargasync.db import connect
from hargasync.extraction import ExtractionError, FixtureExtractor, RunPodExtractor
from hargasync.invoices import InvoiceError, confirm_invoice
from hargasync.matching import AliasRef, ProductRef, match_line, normalize
from hargasync.money import today_my
from tests.support import csrf, login, make_client, open_db
from tests.test_approvals import ApprovalTestCase
from tests.test_invoices import InvoiceTestCase


class TestControlledCatalogueAndTags(ApprovalTestCase):
    """C1: a controlled product can never carry or print a price above its ceiling or without one."""

    def setUp(self):
        super().setUp()
        login(self.client, "owner_ali")

    def add(self, **overrides):
        form = {
            "csrf_token": csrf(self.client, "/catalogue"), "sku": "AYAM-KAMPUNG", "name_bm": "Ayam Kampung (sekilo)",
            "unit": "kg", "cost": "12.00", "price": "15.00", "margin": "15", "controlled_item_code": "ayam_standard",
        }
        form.update(overrides)
        return self.client.post("/catalogue", data=form)

    def exists(self, sku):
        return self.db.execute("SELECT COUNT(*) FROM products WHERE sku = ?", (sku,)).fetchone()[0] == 1

    def test_price_above_ceiling_refused(self):
        page = self.add()
        self.assertEqual(page.status_code, 400)
        self.assertIn("above the ceiling", page.text)
        self.assertFalse(self.exists("AYAM-KAMPUNG"))

    def test_price_without_valid_ceiling_refused(self):
        page = self.add(sku="TELUR-B30", name_bm="Telur Gred B 30 biji", unit="papan", price="20.00",
                        controlled_item_code="telur_gred_a")
        self.assertEqual(page.status_code, 400)
        self.assertIn("No valid ceiling", page.text)
        self.assertFalse(self.exists("TELUR-B30"))

    def test_controlled_product_without_price_allowed(self):
        self.add(price="")
        self.assertTrue(self.exists("AYAM-KAMPUNG"))

    def test_tag_sheet_holds_back_price_above_ceiling(self):
        ayam = self.product_id("AYAM-KG")
        self.db.execute("UPDATE products SET price_sen = 1500 WHERE id = ?", (ayam,))
        page = self.client.get(f"/tags/print?ids={ayam}")
        self.assertNotIn("15.00", page.text.split("Not printed")[0])
        self.assertIn("above the ceiling", page.text)

    def test_tag_sheet_holds_back_controlled_item_without_ceiling(self):
        telur = self.product_id("TELUR-A30")
        page = self.client.get(f"/tags/print?ids={telur}")
        self.assertIn("0 tags", page.text)
        self.assertIn("no valid ceiling", page.text)


class TestZeroCost(ApprovalTestCase):
    """I1: a free (RM 0.00) line never becomes an RM 0.00 price or a 500."""

    def test_zero_cost_line_refused_at_confirm(self):
        self.upload()
        overrides = {p: {"skip": "1"} for p in range(2, 9)}
        overrides[1] = {"cost": "0.00"}
        self.save(2, overrides)
        page = self.client.post("/invoices/2/confirm", data={"csrf_token": csrf(self.client, "/invoices/2")})
        self.assertIn("RM 0.00", page.text)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM price_proposals WHERE invoice_id = 2").fetchone()[0], 0)

    def test_zero_price_proposal_cannot_be_approved(self):
        susu = self.proposal("SUSU-500G")
        self.db.execute(
            "UPDATE price_proposals SET new_cost_sen = 0, suggested_price_sen = 0, proposed_price_sen = 0 WHERE id = ?",
            (susu["id"],),
        )
        login(self.client, "owner_ali")
        response = self.approve("SUSU-500G")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.product("SUSU-500G")["price_sen"], 380)


class SlowExtractor(FixtureExtractor):
    def extract(self, image, mime):
        time.sleep(1.5)
        return super().extract(image, mime)


class TestUploadDoesNotBlockServer(InvoiceTestCase):
    """I2: a slow AI read must not freeze other requests."""

    extractor = SlowExtractor

    def test_other_requests_answer_during_slow_upload(self):
        from fastapi.testclient import TestClient

        from tests.test_invoices import SAMPLE_PNG

        # A context-managed TestClient runs every request on one event loop, like uvicorn does.
        with TestClient(self.client.app) as shared, TestClient(self.client.app) as other:
            shared.portal, other.portal = shared.portal, shared.portal
            login(shared, "staff_mei")
            token = csrf(shared, "/")
            upload = threading.Thread(target=lambda: shared.post(
                "/invoices", data={"csrf_token": token}, files={"photo": ("i.png", SAMPLE_PNG, "image/png")},
            ))
            upload.start()
            time.sleep(0.3)
            started = time.monotonic()
            other.get("/login")
            elapsed = time.monotonic() - started
            upload.join()
        self.assertLess(elapsed, 0.8)


class TestConcurrentConfirm(InvoiceTestCase):
    """I3: two confirms of one invoice create one set of proposals."""

    def test_double_confirm_creates_one_set(self):
        login(self.client, "staff_mei")
        self.upload()
        self.save(1, {
            3: {"product": str(self.product_id("SUSU-500G")), "pack": "24"},
            7: {"product": str(self.product_id("KICAP-340"))},
            8: {"skip": "1"},
        })
        db_path = self.settings.data_dir / "hargasync.db"
        barrier = threading.Barrier(2, timeout=1)
        real = invoices_module.limit_from_row
        outcomes = []

        def gated(row):
            if not getattr(threading.current_thread(), "gated", False):
                threading.current_thread().gated = True
                try:
                    barrier.wait()
                except threading.BrokenBarrierError:
                    pass
            return real(row)

        def run():
            conn = connect(db_path)
            try:
                user = load_user(conn, conn.execute("SELECT id FROM users WHERE username = 'staff_mei'").fetchone()[0])
                outcomes.append(len(confirm_invoice(conn, user, 1, today_my())))
            except InvoiceError:
                outcomes.append("refused")
            finally:
                conn.close()

        with mock.patch.object(invoices_module, "limit_from_row", gated):
            threads = [threading.Thread(target=run) for _ in range(2)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
        self.assertEqual(sorted(outcomes, key=str), [7, "refused"])
        self.assertEqual(self.count("price_proposals"), 7)


class TestNonLatinNames(unittest.TestCase):
    """I4: names in Chinese/Tamil/Jawi keep their letters and never match by an empty alias."""

    PRODUCTS = [ProductRef(1, "GULA-1KG", "Gula Pasir Kasar 1kg", "pek"), ProductRef(2, "MINYAK", "Minyak Masak", "botol")]

    def test_normalize_keeps_non_latin_letters(self):
        self.assertEqual(normalize("白糖 1kg"), "白糖 1kg")
        self.assertNotEqual(normalize("白糖"), normalize("食油"))

    def test_empty_name_never_matches_empty_alias(self):
        result = match_line("!!!", "", self.PRODUCTS, [AliasRef(1, "", "", 1)])
        self.assertEqual((result.product_id, result.status), (None, "unknown"))

    def test_learned_chinese_alias_does_not_capture_other_items(self):
        aliases = [AliasRef(1, normalize("白糖"), normalize("包"), 1)]
        self.assertEqual(match_line("白糖", "包", self.PRODUCTS, aliases).status, "matched")
        self.assertNotEqual(match_line("食油", "瓶", self.PRODUCTS, aliases).status, "matched")


class TestNoEmptyAliasSaved(InvoiceTestCase):
    def test_punctuation_only_name_saves_no_alias(self):
        login(self.client, "staff_mei")
        self.client.post("/invoices", data={"csrf_token": csrf(self.client, "/"), "manual": "1"})
        form = {
            "csrf_token": csrf(self.client, "/invoices/1"), "line_count": "0", "action": "confirm",
            "name_1": "***", "unit_1": "", "qty_1": "1", "cost_1": "2.80",
            "product_1": str(self.product_id("GULA-1KG")), "pack_1": "1",
        }
        self.client.post("/invoices/1/lines", data=form)
        self.assertEqual(self.count("product_aliases"), 0)


class TestApprovalUsesShownPrice(ApprovalTestCase):
    """Re-graded minor: approval never applies a price other than the one on the button."""

    def test_changed_ceiling_refreshes_proposal_instead_of_applying(self):
        self.db.execute("UPDATE price_limits SET max_price_sen = 900 WHERE item_code = 'ayam_standard'")
        login(self.client, "owner_ali")
        page = self.approve("AYAM-KG")
        self.assertIn("changed", page.text)
        self.assertEqual(self.product("AYAM-KG")["price_sen"], 920)
        refreshed = self.proposal("AYAM-KG")
        self.assertEqual((refreshed["status"], refreshed["proposed_price_sen"], refreshed["cap_sen"]), ("pending", 900, 900))
        self.approve("AYAM-KG")
        self.assertEqual(self.product("AYAM-KG")["price_sen"], 900)


class BrokenExtractor:
    source = "runpod"

    def extract(self, image, mime):
        raise RuntimeError("unexpected shape")


class TestUnexpectedExtractorFailure(InvoiceTestCase):
    """Re-graded minor: any AI failure falls back to manual entry, never a 500."""

    extractor = BrokenExtractor

    def test_unexpected_error_opens_manual_entry(self):
        login(self.client, "staff_mei")
        self.assertEqual(self.upload().status_code, 303)
        invoice = self.db.execute("SELECT * FROM invoices").fetchone()
        self.assertEqual((invoice["status"], invoice["extraction_source"]), ("manual", "manual"))
        self.assertIn("unexpected", invoice["extraction_error"])

    def test_runpod_non_object_output_is_extraction_error(self):
        handler = lambda request: httpx.Response(200, json={"status": "COMPLETED", "output": "oops"})
        extractor = RunPodExtractor("k", "e", client=httpx.Client(transport=httpx.MockTransport(handler)))
        with self.assertRaises(ExtractionError):
            extractor.extract(b"x", "image/png")


class TestSecretPlaceholder(unittest.TestCase):
    """Re-graded minor: the example placeholder secret is never used to sign sessions."""

    def test_placeholder_secret_replaced(self):
        with mock.patch.dict(os.environ, {"HARGASYNC_SECRET_KEY": "change-me"}), mock.patch("builtins.print"):
            self.assertNotEqual(load_settings().secret_key, "change-me")

    def test_real_secret_kept(self):
        secret = "s" * 40
        with mock.patch.dict(os.environ, {"HARGASYNC_SECRET_KEY": secret}):
            self.assertEqual(load_settings().secret_key, secret)


if __name__ == "__main__":
    unittest.main()
