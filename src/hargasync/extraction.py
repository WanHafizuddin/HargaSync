"""Invoice reading adapter. The AI only reads the document; it never prices or approves.

Backends: RunPod (production), a labelled fixture (demo without a GPU), or off (manual entry).
Whatever a backend returns is validated by parse_extraction before it reaches the database.
"""

import base64
import json
import time
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

import httpx

from .config import Settings
from .money import MoneyError, parse_rm

FIXTURE_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "invoices" / "sample_invoice.json"
RUNPOD_API = "https://api.runpod.ai/v2"
MAX_LINES = 100
MAX_QTY = Decimal(10000)


class ExtractionError(Exception):
    """The invoice could not be read; the user falls back to manual entry."""


@dataclass(frozen=True)
class ExtractedLine:
    name: str
    unit: str
    qty: Decimal
    unit_cost_sen: int


@dataclass(frozen=True)
class ExtractedInvoice:
    supplier_name: str
    invoice_date: str | None
    lines: list[ExtractedLine]


def _text(value, field: str, max_len: int, required: bool) -> str:
    text = "" if value is None else str(value).strip()
    if required and not text:
        raise ExtractionError(f"Line is missing {field}")
    if len(text) > max_len:
        raise ExtractionError(f"{field} is longer than {max_len} characters")
    return text


def _line(raw, index: int) -> ExtractedLine:
    if not isinstance(raw, dict):
        raise ExtractionError(f"Line {index} is not an object")
    try:
        qty = Decimal(str(raw.get("qty")))
    except InvalidOperation:
        raise ExtractionError(f"Line {index}: quantity is not a number") from None
    if not qty.is_finite() or qty <= 0 or qty > MAX_QTY:
        raise ExtractionError(f"Line {index}: quantity must be above 0 and at most {MAX_QTY}")
    try:
        unit_cost_sen = parse_rm(str(raw.get("unit_cost")))
    except MoneyError:
        raise ExtractionError(f"Line {index}: unit cost {raw.get('unit_cost')!r} is not a valid amount") from None
    return ExtractedLine(
        name=_text(raw.get("name"), "name", 120, required=True),
        unit=_text(raw.get("unit"), "unit", 30, required=False),
        qty=qty,
        unit_cost_sen=unit_cost_sen,
    )


def parse_extraction(payload) -> ExtractedInvoice:
    if not isinstance(payload, dict):
        raise ExtractionError("AI output is not a JSON object")
    lines = payload.get("lines")
    if not isinstance(lines, list):
        raise ExtractionError("AI output has no list of lines")
    if len(lines) > MAX_LINES:
        raise ExtractionError(f"AI output has more than {MAX_LINES} lines")
    invoice_date = payload.get("invoice_date")
    try:
        invoice_date = date.fromisoformat(str(invoice_date)).isoformat() if invoice_date else None
    except ValueError:
        invoice_date = None
    return ExtractedInvoice(
        supplier_name=_text(payload.get("supplier_name"), "supplier name", 120, required=False),
        invoice_date=invoice_date,
        lines=[_line(raw, i + 1) for i, raw in enumerate(lines)],
    )


class RunPodExtractor:
    source = "runpod"

    def __init__(
        self,
        api_key: str,
        endpoint_id: str,
        client: httpx.Client | None = None,
        timeout_s: float = 120,
        poll_interval_s: float = 2.0,
    ):
        self.api_key = api_key
        self.endpoint_id = endpoint_id
        self.client = client or httpx.Client(timeout=95)
        self.timeout_s = timeout_s
        self.poll_interval_s = poll_interval_s

    def _call(self, method: str, path: str, **kwargs) -> dict:
        url = f"{RUNPOD_API}/{self.endpoint_id}/{path}"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            response = self.client.request(method, url, headers=headers, **kwargs)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ExtractionError(f"RunPod request failed: {exc.__class__.__name__}") from exc

    def extract(self, image: bytes, mime: str) -> ExtractedInvoice:
        deadline = time.monotonic() + self.timeout_s
        body = {"input": {"image_base64": base64.b64encode(image).decode("ascii"), "mime": mime}}
        job = self._call("POST", "runsync", json=body)
        while job.get("status") in ("IN_QUEUE", "IN_PROGRESS"):
            if time.monotonic() >= deadline:
                raise ExtractionError("RunPod did not finish in time (the GPU may be starting up)")
            time.sleep(self.poll_interval_s)
            job = self._call("GET", f"status/{job.get('id')}")
        if job.get("status") != "COMPLETED":
            raise ExtractionError(f"RunPod job ended with status {job.get('status')!r}")
        output = job.get("output") or {}
        if "error" in output or "invoice" not in output:
            raise ExtractionError(f"AI could not read the invoice: {output.get('error', 'no invoice in output')}")
        return parse_extraction(output["invoice"])


class FixtureExtractor:
    """Returns a canned extraction. The UI labels it 'Simulated AI'."""

    source = "fixture"

    def __init__(self, json_path: Path = FIXTURE_PATH):
        self.json_path = Path(json_path)

    def extract(self, image: bytes, mime: str) -> ExtractedInvoice:
        return parse_extraction(json.loads(self.json_path.read_text(encoding="utf-8")))


class DisabledExtractor:
    source = "manual"

    def extract(self, image: bytes, mime: str) -> ExtractedInvoice:
        raise ExtractionError("AI reading is not configured")


def build_extractor(settings: Settings):
    if settings.ai_mode == "runpod":
        if not (settings.runpod_api_key and settings.runpod_endpoint_id):
            raise ValueError("AI_MODE=runpod needs RUNPOD_API_KEY and RUNPOD_ENDPOINT_ID")
        return RunPodExtractor(settings.runpod_api_key, settings.runpod_endpoint_id)
    if settings.ai_mode == "fixture":
        return FixtureExtractor()
    return DisabledExtractor()
