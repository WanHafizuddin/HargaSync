"""Regulated price ceilings: which limit, if any, applies to an item today."""

from dataclasses import dataclass
from datetime import date
from typing import Iterable


@dataclass(frozen=True)
class PriceLimit:
    id: int
    item_code: str
    unit: str
    district: str
    retail_level: str
    max_price_sen: int
    valid_from: date
    valid_to: date
    verification: str  # 'verified' or 'demo'
    source_ref: str


def find_applicable_limit(
    limits: Iterable[PriceLimit],
    item_code: str,
    unit: str,
    district: str,
    retail_level: str,
    on: date,
) -> PriceLimit | None:
    """Exact item, unit, district and retail level, valid on the date. Lowest ceiling wins."""
    matches = [
        lim for lim in limits
        if lim.item_code == item_code
        and lim.unit == unit
        and lim.district == district
        and lim.retail_level == retail_level
        and lim.valid_from <= on <= lim.valid_to
    ]
    return min(matches, key=lambda lim: lim.max_price_sen, default=None)


def limit_from_row(row) -> PriceLimit:
    return PriceLimit(
        id=row["id"],
        item_code=row["item_code"],
        unit=row["unit"],
        district=row["district"],
        retail_level=row["retail_level"],
        max_price_sen=row["max_price_sen"],
        valid_from=date.fromisoformat(row["valid_from"]),
        valid_to=date.fromisoformat(row["valid_to"]),
        verification=row["verification"],
        source_ref=row["source_ref"],
    )
