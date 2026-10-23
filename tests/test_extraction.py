import json
import unittest
from decimal import Decimal
from pathlib import Path

import httpx

from hargasync.extraction import (
    FIXTURE_PATH,
    DisabledExtractor,
    ExtractionError,
    FixtureExtractor,
    RunPodExtractor,
    parse_extraction,
)

VALID = {
    "supplier_name": "Syarikat Borong Maju Jaya",
    "invoice_date": "2026-10-22",
    "lines": [
        {"name": "Gula Pasir Kasar 1kg", "unit": "pek", "qty": 20, "unit_cost": "RM 4.50"},
        {"name": "Ayam Standard", "unit": "kg", "qty": "1.5", "unit_cost": 8.6},
    ],
}


def payload_with_line(**line):
    base = {"name": "Item", "unit": "pek", "qty": 1, "unit_cost": 1}
    base.update(line)
    return {"supplier_name": "S", "lines": [base]}


class TestParseExtraction(unittest.TestCase):
    def test_valid_payload(self):
        invoice = parse_extraction(VALID)
        self.assertEqual(invoice.supplier_name, "Syarikat Borong Maju Jaya")
        self.assertEqual(invoice.invoice_date, "2026-10-22")
        self.assertEqual(invoice.lines[0].unit_cost_sen, 450)
        self.assertEqual(invoice.lines[0].qty, Decimal("20"))
        self.assertEqual(invoice.lines[1].unit_cost_sen, 860)
        self.assertEqual(invoice.lines[1].qty, Decimal("1.5"))

    def test_zero_qty_rejected(self):
        with self.assertRaises(ExtractionError):
            parse_extraction(payload_with_line(qty=0))

    def test_huge_qty_rejected(self):
        with self.assertRaises(ExtractionError):
            parse_extraction(payload_with_line(qty=10001))

    def test_negative_cost_rejected(self):
        with self.assertRaises(ExtractionError):
            parse_extraction(payload_with_line(unit_cost=-1))

    def test_empty_name_rejected(self):
        with self.assertRaises(ExtractionError):
            parse_extraction(payload_with_line(name="  "))

    def test_too_many_lines_rejected(self):
        payload = {"supplier_name": "S", "lines": [{"name": "x", "unit": "pek", "qty": 1, "unit_cost": 1}] * 101}
        with self.assertRaises(ExtractionError):
            parse_extraction(payload)

    def test_not_a_dict_rejected(self):
        with self.assertRaises(ExtractionError):
            parse_extraction(["lines"])

    def test_bad_date_becomes_none(self):
        payload = dict(VALID, invoice_date="22/10/2026")
        self.assertIsNone(parse_extraction(payload).invoice_date)


def runpod_extractor(handler):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return RunPodExtractor("key", "endpoint-1", client=client, poll_interval_s=0)


class TestRunPodExtractor(unittest.TestCase):
    def test_completed_job(self):
        def handler(request):
            self.assertEqual(request.url.path, "/v2/endpoint-1/runsync")
            self.assertEqual(request.headers["authorization"], "Bearer key")
            body = json.loads(request.content)
            self.assertEqual(body["input"]["mime"], "image/png")
            return httpx.Response(200, json={"id": "j1", "status": "COMPLETED", "output": {"invoice": VALID}})

        invoice = runpod_extractor(handler).extract(b"png-bytes", "image/png")
        self.assertEqual(len(invoice.lines), 2)

    def test_queued_job_is_polled(self):
        calls = []

        def handler(request):
            calls.append(request.url.path)
            if request.url.path.endswith("/runsync"):
                return httpx.Response(200, json={"id": "j2", "status": "IN_QUEUE"})
            if len(calls) < 3:
                return httpx.Response(200, json={"id": "j2", "status": "IN_PROGRESS"})
            return httpx.Response(200, json={"id": "j2", "status": "COMPLETED", "output": {"invoice": VALID}})

        invoice = runpod_extractor(handler).extract(b"x", "image/jpeg")
        self.assertEqual(invoice.supplier_name, "Syarikat Borong Maju Jaya")
        self.assertEqual(calls[1:], ["/v2/endpoint-1/status/j2", "/v2/endpoint-1/status/j2"])

    def test_failed_job_raises(self):
        handler = lambda request: httpx.Response(200, json={"id": "j3", "status": "FAILED", "error": "OOM"})
        with self.assertRaises(ExtractionError):
            runpod_extractor(handler).extract(b"x", "image/jpeg")

    def test_http_error_raises(self):
        handler = lambda request: httpx.Response(500, text="boom")
        with self.assertRaises(ExtractionError):
            runpod_extractor(handler).extract(b"x", "image/jpeg")

    def test_worker_error_output_raises(self):
        handler = lambda request: httpx.Response(200, json={"status": "COMPLETED", "output": {"error": "no JSON"}})
        with self.assertRaises(ExtractionError):
            runpod_extractor(handler).extract(b"x", "image/jpeg")

    def test_timeout_raises(self):
        handler = lambda request: httpx.Response(200, json={"id": "j4", "status": "IN_QUEUE"})
        extractor = runpod_extractor(handler)
        extractor.timeout_s = 0
        with self.assertRaises(ExtractionError):
            extractor.extract(b"x", "image/jpeg")


class TestOtherExtractors(unittest.TestCase):
    def test_fixture_extractor(self):
        extractor = FixtureExtractor(FIXTURE_PATH)
        self.assertEqual(extractor.source, "fixture")
        expected = json.loads(Path(FIXTURE_PATH).read_text(encoding="utf-8"))
        invoice = extractor.extract(b"ignored", "image/png")
        self.assertEqual([l.name for l in invoice.lines], [l["name"] for l in expected["lines"]])

    def test_disabled_extractor_raises(self):
        with self.assertRaises(ExtractionError):
            DisabledExtractor().extract(b"x", "image/png")


if __name__ == "__main__":
    unittest.main()
