"""Draw fixtures/invoices/sample_invoice.png from sample_invoice.json (fictional demo invoice).

Run: python scripts/make_sample_invoice.py
"""

import json
from decimal import Decimal
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "fixtures" / "invoices" / "sample_invoice.json"
OUTPUT = FIXTURE.with_suffix(".png")


def font(size: int, bold: bool = False):
    for name in (("arialbd.ttf", "DejaVuSans-Bold.ttf") if bold else ("arial.ttf", "DejaVuSans.ttf")):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def main() -> None:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    image = Image.new("RGB", (1000, 1300), (252, 251, 247))
    draw = ImageDraw.Draw(image)
    ink = (30, 30, 30)

    draw.text((60, 50), data["supplier_name"], font=font(30, bold=True), fill=ink)
    draw.text((60, 95), "No. 12, Jalan Perusahaan 3, 47100 Puchong, Selangor  |  Tel: 03-0000 0000", font=font(18), fill=ink)
    draw.text((60, 150), "INVOIS / INVOICE", font=font(26, bold=True), fill=ink)
    draw.text((640, 150), "No: INV-DEMO-0042", font=font(20), fill=ink)
    draw.text((640, 180), f"Tarikh: {data['invoice_date']}", font=font(20), fill=ink)
    draw.text((60, 200), "Kepada: Kedai Runcit Pak Ali (DEMO), Petaling Jaya", font=font(20), fill=ink)

    columns = [(60, "Perkara / Item"), (470, "Unit"), (590, "Kuantiti"), (720, "Harga Seunit"), (870, "Jumlah")]
    top = 270
    draw.line((50, top - 10, 950, top - 10), fill=ink, width=2)
    for x, label in columns:
        draw.text((x, top), label, font=font(19, bold=True), fill=ink)
    draw.line((50, top + 35, 950, top + 35), fill=ink, width=2)

    total = Decimal(0)
    y = top + 55
    for line in data["lines"]:
        unit_cost = Decimal(str(line["unit_cost"]))
        amount = unit_cost * Decimal(str(line["qty"]))
        total += amount
        row = [line["name"], line["unit"], str(line["qty"]), f"{unit_cost:.2f}", f"{amount:.2f}"]
        for (x, _), value in zip(columns, row):
            draw.text((x, y), value, font=font(20), fill=ink)
        y += 52

    draw.line((50, y, 950, y), fill=ink, width=2)
    draw.text((640, y + 20), "JUMLAH (RM)", font=font(21, bold=True), fill=ink)
    draw.text((860, y + 20), f"{total:.2f}", font=font(21, bold=True), fill=ink)
    draw.text((60, 1220), "Contoh invois rekaan untuk demo HargaSync. Fictional invoice for demo only.", font=font(17), fill=(110, 110, 110))

    image = image.rotate(-1.2, expand=False, fillcolor=(235, 233, 226))
    image.save(OUTPUT, optimize=True)
    print(f"wrote {OUTPUT} (total RM {total:.2f})")


if __name__ == "__main__":
    main()
