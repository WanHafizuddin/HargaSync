"""Money helpers. All amounts are integer sen; arithmetic uses Decimal."""

import re
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal

MY_TZ = timezone(timedelta(hours=8), "MYT")

_RM_PATTERN = re.compile(r"^(?:rm\s*)?(\d{1,7})(?:\.(\d{1,2}))?$", re.IGNORECASE)


class MoneyError(ValueError):
    """Raised for an amount or margin that cannot be used."""


def parse_rm(text: str) -> int:
    """Parse "RM12.50", "12.5" or " 12.50 " into sen. Rejects commas, negatives and 3+ decimals."""
    match = _RM_PATTERN.match((text or "").strip())
    if not match:
        raise MoneyError(f"Not a valid ringgit amount: {text!r} (use e.g. 12.50)")
    ringgit, cents = match.group(1), (match.group(2) or "0").ljust(2, "0")
    return int(ringgit) * 100 + int(cents)


def format_rm(sen: int) -> str:
    return f"RM {sen // 100}.{sen % 100:02d}"


def round_up_10_sen(value: Decimal) -> int:
    """Round an amount in sen up to the next multiple of 10 sen."""
    tens = (value / 10).to_integral_value(rounding=ROUND_CEILING)
    return int(tens) * 10


def round_half_up_sen(value: Decimal) -> int:
    return int(value.to_integral_value(rounding=ROUND_HALF_UP))


def price_from_margin(cost_sen: int, margin: Decimal) -> int:
    """Target selling price = cost / (1 - margin), rounded up to RM0.10."""
    if margin < 0 or margin >= 1:
        raise MoneyError(f"Target margin must be at least 0 and below 1, got {margin}")
    return round_up_10_sen(Decimal(cost_sen) / (Decimal(1) - margin))


def today_my() -> date:
    return datetime.now(MY_TZ).date()
