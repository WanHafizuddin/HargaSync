import unittest
from datetime import date
from decimal import Decimal

from hargasync.limits import PriceLimit, find_applicable_limit
from hargasync.pricing import ProposalInput, compute_proposal, role_can_approve

TODAY = date(2026, 10, 23)


def limit(**overrides):
    values = dict(
        id=1, item_code="ayam_standard", unit="kg", district="Petaling", retail_level="runcit",
        max_price_sen=900, valid_from=date(2026, 10, 1), valid_to=date(2026, 11, 30),
        verification="verified", source_ref="Warta Kerajaan P.U.(A) 123/2026",
    )
    values.update(overrides)
    return PriceLimit(**values)


def find(limits, **overrides):
    args = dict(item_code="ayam_standard", unit="kg", district="Petaling", retail_level="runcit", on=TODAY)
    args.update(overrides)
    return find_applicable_limit(limits, **args)


def proposal(**overrides):
    values = dict(
        old_cost_sen=1000, new_cost_sen=1000, current_price_sen=1250,
        target_margin=Decimal("0.20"), controlled=False, limit=None,
    )
    values.update(overrides)
    return compute_proposal(ProposalInput(**values))


class TestFindApplicableLimit(unittest.TestCase):
    def test_exact_match_found(self):
        self.assertEqual(find([limit()]).id, 1)

    def test_wrong_district_ignored(self):
        self.assertIsNone(find([limit(district="Klang")]))

    def test_wrong_unit_ignored(self):
        self.assertIsNone(find([limit(unit="ekor")]))

    def test_expired_ignored(self):
        self.assertIsNone(find([limit(valid_to=date(2026, 10, 22))]))

    def test_not_yet_valid_ignored(self):
        self.assertIsNone(find([limit(valid_from=date(2026, 10, 24))]))

    def test_lowest_ceiling_wins(self):
        found = find([limit(id=1, max_price_sen=950), limit(id=2, max_price_sen=900)])
        self.assertEqual(found.id, 2)


class TestCostJump(unittest.TestCase):
    def test_exactly_fifteen_percent_not_flagged(self):
        self.assertNotIn("cost_jump", proposal(new_cost_sen=1150).flags)

    def test_over_fifteen_percent_flagged(self):
        result = proposal(new_cost_sen=1160)
        self.assertIn("cost_jump", result.flags)
        self.assertEqual(result.required_role, "owner")

    def test_zero_old_cost_does_not_crash(self):
        result = proposal(old_cost_sen=0, new_cost_sen=500)
        self.assertNotIn("cost_jump", result.flags)


class TestRouting(unittest.TestCase):
    def test_unchanged_price_is_staff(self):
        result = proposal()
        self.assertEqual(result.suggested_price_sen, 1250)
        self.assertEqual(result.proposed_price_sen, 1250)
        self.assertEqual(result.required_role, "staff")
        self.assertEqual(result.status, "pending")

    def test_five_percent_change_is_staff(self):
        result = proposal(old_cost_sen=840, new_cost_sen=840, current_price_sen=1000)
        self.assertEqual(result.proposed_price_sen, 1050)
        self.assertEqual(result.required_role, "staff")

    def test_over_five_percent_is_owner(self):
        result = proposal(old_cost_sen=848, new_cost_sen=848, current_price_sen=1000)
        self.assertEqual(result.proposed_price_sen, 1060)
        self.assertIn("large_change", result.flags)
        self.assertEqual(result.required_role, "owner")

    def test_new_product_is_owner(self):
        result = proposal(current_price_sen=None)
        self.assertIn("new_product", result.flags)
        self.assertEqual(result.required_role, "owner")


class TestCeilings(unittest.TestCase):
    def test_verified_cap_applied(self):
        result = proposal(controlled=True, limit=limit(max_price_sen=900))
        self.assertEqual(result.suggested_price_sen, 1250)
        self.assertEqual(result.cap_sen, 900)
        self.assertEqual(result.proposed_price_sen, 900)
        for flag in ("capped", "controlled", "below_cost"):
            self.assertIn(flag, result.flags)
        self.assertEqual(result.required_role, "owner")
        self.assertTrue(any("Warta Kerajaan" in line for line in result.explanation))

    def test_cap_above_suggestion_not_capped(self):
        result = proposal(controlled=True, limit=limit(max_price_sen=1500))
        self.assertEqual(result.proposed_price_sen, 1250)
        self.assertNotIn("capped", result.flags)
        self.assertEqual(result.required_role, "owner")

    def test_demo_ceiling_labelled(self):
        result = proposal(controlled=True, limit=limit(verification="demo", source_ref="demo fixture"))
        self.assertIn("demo_ceiling", result.flags)
        self.assertTrue(any("DEMO — fictional ceiling" in line for line in result.explanation))

    def test_controlled_without_limit_is_blocked(self):
        result = proposal(controlled=True, limit=None)
        self.assertEqual(result.status, "blocked")
        self.assertIsNone(result.proposed_price_sen)
        self.assertIn("no_valid_ceiling", result.flags)
        self.assertEqual(result.required_role, "owner")

    def test_explanation_shows_formula(self):
        result = proposal()
        self.assertTrue(any("RM 10.00" in line and "RM 12.50" in line for line in result.explanation))


class TestRoleCanApprove(unittest.TestCase):
    def test_matrix(self):
        self.assertFalse(role_can_approve("staff", "owner"))
        self.assertTrue(role_can_approve("staff", "staff"))
        self.assertTrue(role_can_approve("owner", "staff"))
        self.assertTrue(role_can_approve("owner", "owner"))
        self.assertFalse(role_can_approve("auditor", "staff"))


if __name__ == "__main__":
    unittest.main()
