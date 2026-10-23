import unittest

from hargasync.matching import AliasRef, ProductRef, match_line, normalize

PRODUCTS = [
    ProductRef(id=1, sku="GULA-1KG", name_bm="Gula Pasir 1kg", unit="pek"),
    ProductRef(id=2, sku="MINYAK-5KG", name_bm="Minyak Masak Botol 5kg", unit="botol"),
    ProductRef(id=3, sku="SUSU-PEKAT", name_bm="Susu Pekat Manis 500g", unit="tin"),
]
ALIASES = [AliasRef(product_id=3, alias_norm="susu pekat manis 500g", unit_norm="karton", pack_size=24)]


class TestNormalize(unittest.TestCase):
    def test_lowercase_strip_punctuation(self):
        self.assertEqual(normalize("  Gula Pasir, 1KG "), "gula pasir 1kg")

    def test_accents_removed(self):
        self.assertEqual(normalize("Café-Ais"), "cafe ais")


class TestMatchLine(unittest.TestCase):
    def test_alias_hit_uses_pack_size(self):
        result = match_line("SUSU PEKAT MANIS 500G", "Karton", PRODUCTS, ALIASES)
        self.assertEqual((result.product_id, result.status, result.pack_size), (3, "matched", 24))

    def test_exact_name_same_unit_matched(self):
        result = match_line("Gula Pasir 1kg", "pek", PRODUCTS, ALIASES)
        self.assertEqual((result.product_id, result.status, result.pack_size), (1, "matched", 1))

    def test_exact_sku_matched(self):
        result = match_line("minyak-5kg", "Botol", PRODUCTS, ALIASES)
        self.assertEqual((result.product_id, result.status), (2, "matched"))

    def test_exact_name_different_unit_uncertain(self):
        result = match_line("Gula Pasir 1kg", "guni", PRODUCTS, ALIASES)
        self.assertEqual((result.product_id, result.status), (1, "uncertain"))

    def test_typo_is_uncertain(self):
        result = match_line("Gula Pasr 1kg", "pek", PRODUCTS, ALIASES)
        self.assertEqual((result.product_id, result.status), (1, "uncertain"))
        self.assertLess(result.score, 1.0)

    def test_unrelated_is_unknown(self):
        result = match_line("Barang Lain", "pek", PRODUCTS, ALIASES)
        self.assertEqual((result.product_id, result.status), (None, "unknown"))


if __name__ == "__main__":
    unittest.main()
