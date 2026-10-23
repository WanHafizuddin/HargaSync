"""Print HargaSync's measured evidence: planted-breach interception and invoice-reading accuracy.

Run: python scripts/benchmark.py
Uses AI_MODE / RUNPOD_* from the environment for the reading benchmark (fixture mode is labelled).
"""

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from hargasync.benchmark import BREACHES_PATH, run_breach_benchmark, run_extraction_benchmark  # noqa: E402
from hargasync.config import load_settings  # noqa: E402
from hargasync.extraction import FIXTURE_PATH, build_extractor  # noqa: E402


def main() -> None:
    print(f"HargaSync benchmark, run {datetime.now():%Y-%m-%d %H:%M}")
    breaches = run_breach_benchmark(BREACHES_PATH)
    print(f"\nPlanted rule breaches ({BREACHES_PATH.name}): {breaches['intercepted']}/{breaches['cases']} intercepted"
          f" ({breaches['rate']:.0%})")
    for name in breaches["failures"]:
        print(f"  MISSED: {name}")

    extractor = build_extractor(load_settings())
    reading = run_extraction_benchmark(extractor, FIXTURE_PATH.parent)
    label = " (Simulated AI: fixture returns the expected answer, not a real measurement)" if reading["source"] == "fixture" else ""
    print(f"\nInvoice reading on {reading['invoices']} fixture invoice(s), source {reading['source']}{label}:")
    print(f"  {reading['correct_lines']}/{reading['lines']} lines exactly right ({reading['line_accuracy']:.0%})")
    for error in reading["errors"]:
        print(f"  ERROR: {error}")


if __name__ == "__main__":
    main()
