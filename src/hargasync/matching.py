"""Match an invoice line to a catalogue product. Uncertain results always go to a human."""

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

FUZZY_THRESHOLD = 0.6


@dataclass(frozen=True)
class ProductRef:
    id: int
    sku: str
    name_bm: str
    unit: str


@dataclass(frozen=True)
class AliasRef:
    product_id: int
    alias_norm: str
    unit_norm: str
    pack_size: int


@dataclass(frozen=True)
class MatchResult:
    product_id: int | None
    status: str  # 'matched', 'uncertain' or 'unknown'
    score: float
    pack_size: int = 1


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    text = re.sub(r"[\W_]+", " ", text)
    return text.strip()


def match_line(raw_name: str, raw_unit: str, products: list[ProductRef], aliases: list[AliasRef]) -> MatchResult:
    name, unit = normalize(raw_name), normalize(raw_unit)
    if not name:
        return MatchResult(None, "unknown", 0.0)
    by_id = {p.id: p for p in products}

    for alias in aliases:
        if alias.alias_norm == name and alias.unit_norm == unit and alias.product_id in by_id:
            return MatchResult(alias.product_id, "matched", 1.0, alias.pack_size)

    for product in products:
        if name in (normalize(product.sku), normalize(product.name_bm)):
            status = "matched" if normalize(product.unit) == unit else "uncertain"
            return MatchResult(product.id, status, 1.0)

    best_id, best_score = None, 0.0
    candidates = [(p.id, normalize(p.name_bm)) for p in products]
    candidates += [(a.product_id, a.alias_norm) for a in aliases if a.product_id in by_id]
    for product_id, candidate in candidates:
        score = SequenceMatcher(None, name, candidate).ratio()
        if score > best_score:
            best_id, best_score = product_id, score
    if best_score >= FUZZY_THRESHOLD:
        return MatchResult(best_id, "uncertain", round(best_score, 3))
    return MatchResult(None, "unknown", round(best_score, 3))
