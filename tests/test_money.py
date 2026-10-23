import unittest
from decimal import Decimal

from hargasync.money import MoneyError, format_rm, parse_rm, price_from_margin, round_up_10_sen


class TestPriceFromMargin(unittest.TestCase):
    def test_exact_result_is_kept(self):
        self.assertEqual(price_from_margin(1000, Decimal("0.20")), 1250)

    def test_rounds_up_to_next_10_sen(self):
        self.assertEqual(price_from_margin(1003, Decimal("0.25")), 1340)

    def test_ten_percent_margin(self):
        self.assertEqual(price_from_margin(1170, Decimal("0.10")), 1300)

    def test_zero_margin_is_cost(self):
        self.assertEqual(price_from_margin(1000, Decimal("0")), 1000)

    def test_margin_of_one_is_rejected(self):
        with self.assertRaises(MoneyError):
            price_from_margin(1000, Decimal("1"))

    def test_negative_margin_is_rejected(self):
        with self.assertRaises(MoneyError):
            price_from_margin(1000, Decimal("-0.01"))


class TestRoundUp(unittest.TestCase):
    def test_multiple_of_ten_unchanged(self):
        self.assertEqual(round_up_10_sen(Decimal("1250")), 1250)

    def test_any_fraction_rounds_up(self):
        self.assertEqual(round_up_10_sen(Decimal("1250.0001")), 1260)


class TestParseRm(unittest.TestCase):
    def test_accepted_forms(self):
        for text in ("RM12.50", "12.5", " 12.50 ", "rm 12.50"):
            with self.subTest(text=text):
                self.assertEqual(parse_rm(text), 1250)

    def test_rejected_forms(self):
        for text in ("12,50", "abc", "-1", "1.234", ""):
            with self.subTest(text=text):
                with self.assertRaises(MoneyError):
                    parse_rm(text)


class TestFormatRm(unittest.TestCase):
    def test_format(self):
        self.assertEqual(format_rm(1230), "RM 12.30")

    def test_format_small(self):
        self.assertEqual(format_rm(5), "RM 0.05")


if __name__ == "__main__":
    unittest.main()
