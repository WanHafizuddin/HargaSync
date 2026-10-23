"""Evidence for the pitch: planted rule breaches and invoice-reading accuracy, measured on fixtures."""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from .extraction import ExtractionError, parse_extraction
from .limits import PriceLimit, find_applicable_limit
from .matching import normalize
from .pricing import ProposalInput, compute_proposal

BREACHES_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "breaches.json"


def _limit(template: dict, overrides: dict) -> PriceLimit:
    values = {**template, **overrides}
    values["valid_from"] = date.fromisoformat(values["valid_from"])
    values["valid_to"] = date.fromisoformat(values["valid_to"])
    return PriceLimit(**values)


def _intercepted(result, expect: dict) -> bool:
    checks = []
    if "flag" in expect:
        checks.append(expect["flag"] in result.flags)
    if "status" in expect:
        checks.append(result.status == expect["status"])
    if "required_role" in expect:
        checks.append(result.required_role == expect["required_role"])
    if "max_price_sen" in expect:
        checks.append(result.proposed_price_sen is not None and result.proposed_price_sen <= expect["max_price_sen"])
    return bool(checks) and all(checks)


def run_breach_benchmark(path: Path = BREACHES_PATH) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    item = data["item"]
    on = date.fromisoformat(item["on"])
    failures = []
    for case in data["cases"]:
        limits = [] if case["limit"] is None else [_limit(data["limit_template"], case["limit"])]
        limit = find_applicable_limit(limits, item["code"], item["unit"], item["district"], item["retail_level"], on)
        result = compute_proposal(ProposalInput(
            old_cost_sen=case["old_cost_sen"],
            new_cost_sen=case["new_cost_sen"],
            current_price_sen=case["current_price_sen"],
            target_margin=Decimal(case["target_margin"]),
            controlled=case["controlled"],
            limit=limit,
        ))
        if not _intercepted(result, case["expect"]):
            failures.append(case["name"])
    total = len(data["cases"])
    caught = total - len(failures)
    return {"cases": total, "intercepted": caught, "rate": caught / total if total else 0.0, "failures": failures}


def _line_key(line) -> tuple:
    return normalize(line.name), line.qty, line.unit_cost_sen


def run_extraction_benchmark(extractor, fixtures_dir: Path) -> dict:
    """Compare the extractor's lines with each fixture's expected JSON (name, qty and unit cost must all match)."""
    invoices = lines = correct = 0
    errors = []
    for expected_path in sorted(Path(fixtures_dir).glob("*.json")):
        image_path = next((p for p in expected_path.parent.glob(expected_path.stem + ".*") if p.suffix != ".json"), None)
        if image_path is None:
            continue
        expected = parse_extraction(json.loads(expected_path.read_text(encoding="utf-8")))
        mime = {".png": "image/png", ".webp": "image/webp"}.get(image_path.suffix.lower(), "image/jpeg")
        invoices += 1
        lines += len(expected.lines)
        try:
            got = extractor.extract(image_path.read_bytes(), mime)
        except ExtractionError as exc:
            errors.append(f"{image_path.name}: {exc}")
            continue
        remaining = [_line_key(line) for line in got.lines]
        for line in expected.lines:
            key = _line_key(line)
            if key in remaining:
                remaining.remove(key)
                correct += 1
    return {
        "source": extractor.source,
        "invoices": invoices,
        "lines": lines,
        "correct_lines": correct,
        "line_accuracy": correct / lines if lines else 0.0,
        "errors": errors,
    }
