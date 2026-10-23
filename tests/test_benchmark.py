import json
import unittest

from hargasync.benchmark import BREACHES_PATH, run_breach_benchmark, run_extraction_benchmark
from hargasync.extraction import FIXTURE_PATH, FixtureExtractor


class TestBenchmarks(unittest.TestCase):
    def test_every_planted_breach_is_intercepted(self):
        result = run_breach_benchmark(BREACHES_PATH)
        self.assertGreaterEqual(result["cases"], 10)
        self.assertEqual(result["failures"], [])
        self.assertEqual(result["rate"], 1.0)

    def test_benchmark_reports_a_missed_breach(self, tmp_name="missed.json"):
        cases = json.loads(BREACHES_PATH.read_text(encoding="utf-8"))
        cases["cases"] = [dict(cases["cases"][0], expect={"flag": "no_such_flag"})]
        path = BREACHES_PATH.with_name(tmp_name)
        self.addCleanup(path.unlink, missing_ok=True)
        path.write_text(json.dumps(cases), encoding="utf-8")
        result = run_breach_benchmark(path)
        self.assertEqual((result["cases"], result["intercepted"], result["rate"]), (1, 0, 0.0))

    def test_extraction_benchmark_on_fixture(self):
        result = run_extraction_benchmark(FixtureExtractor(), FIXTURE_PATH.parent)
        self.assertEqual(result["invoices"], 1)
        self.assertEqual(result["lines"], 8)
        self.assertEqual(result["line_accuracy"], 1.0)


if __name__ == "__main__":
    unittest.main()
