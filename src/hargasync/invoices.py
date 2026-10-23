"""Invoice intake, human review and turning reviewed lines into price proposals."""

import io
import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from PIL import Image

from .audit import log_event
from .auth import CurrentUser
from .db import now_iso, transaction
from .extraction import ExtractedInvoice, ExtractionError
from .limits import find_applicable_limit, limit_from_row
from .matching import AliasRef, ProductRef, match_line, normalize
from .money import round_half_up_sen
from .pricing import ProposalInput, compute_proposal

MAX_UPLOAD_BYTES = 8 * 1024 * 1024
IMAGE_FORMATS = {"JPEG": ("image/jpeg", "jpg"), "PNG": ("image/png", "png"), "WEBP": ("image/webp", "webp")}
UNRESOLVED = ("uncertain", "unknown")


class UploadError(ValueError):
    """The uploaded file was refused; nothing was stored."""


class InvoiceError(ValueError):
    """A review or confirm step was refused, with a message for the user."""


@dataclass(frozen=True)
class LineEdit:
    position: int
    raw_name: str
    raw_unit: str
    qty: Decimal
    unit_cost_sen: int
    product_id: int | None
    pack_size: int
    skip: bool


def validate_image(data: bytes) -> str:
    """Return the MIME type of a JPEG, PNG or WebP image no larger than 8 MB."""
    if not data:
        raise UploadError("Choose an invoice photo to upload.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise UploadError("That photo is larger than 8 MB. Take it again at a lower resolution.")
    try:
        with Image.open(io.BytesIO(data)) as image:
            image_format = image.format
            image.verify()
    except Exception:
        raise UploadError("That file is not a JPEG, PNG or WebP image.") from None
    if image_format not in IMAGE_FORMATS:
        raise UploadError("That file is not a JPEG, PNG or WebP image.")
    return IMAGE_FORMATS[image_format][0]


def get_invoice(conn: sqlite3.Connection, shop_id: int, invoice_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM invoices WHERE id = ? AND shop_id = ?", (invoice_id, shop_id)).fetchone()


def load_catalogue(conn: sqlite3.Connection, shop_id: int) -> tuple[list[ProductRef], list[AliasRef]]:
    products = [
        ProductRef(r["id"], r["sku"], r["name_bm"], r["unit"])
        for r in conn.execute("SELECT id, sku, name_bm, unit FROM products WHERE shop_id = ?", (shop_id,))
    ]
    aliases = [
        AliasRef(r["product_id"], r["alias_norm"], r["unit_norm"], r["pack_size"])
        for r in conn.execute(
            "SELECT product_id, alias_norm, unit_norm, pack_size FROM product_aliases WHERE shop_id = ?", (shop_id,)
        )
    ]
    return products, aliases


def _insert_line(conn, invoice_id, position, name, unit, qty, cost_sen, product_id, pack_size, status, score):
    conn.execute(
        "INSERT INTO invoice_lines (invoice_id, position, raw_name, raw_unit, qty, unit_cost_sen, product_id,"
        " pack_size, match_status, match_score) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (invoice_id, position, name, unit, str(qty), cost_sen, product_id, pack_size, status, score),
    )


def create_invoice(
    conn: sqlite3.Connection, user: CurrentUser, image: bytes | None, extractor, data_dir: Path
) -> int:
    """Store the photo privately, let the AI read it, match lines. AI failure means manual entry."""
    extracted: ExtractedInvoice | None = None
    error = None
    mime = image_rel = None
    if image is not None:
        mime = validate_image(image)
        try:
            extracted = extractor.extract(image, mime)
        except ExtractionError as exc:
            error = str(exc)
        except Exception as exc:  # adapter boundary: any AI failure means manual entry, never a 500
            error = f"AI reading failed unexpectedly ({exc.__class__.__name__})"
        ext = next(e for m, e in IMAGE_FORMATS.values() if m == mime)
        image_rel = f"uploads/{user.shop_id}/{uuid.uuid4().hex}.{ext}"

    image_file = data_dir / image_rel if image_rel else None
    if image_file is not None:
        image_file.parent.mkdir(parents=True, exist_ok=True)
        image_file.write_bytes(image)
    try:
        products, aliases = load_catalogue(conn, user.shop_id)
        has_lines = extracted is not None and len(extracted.lines) > 0
        with transaction(conn):
            invoice_id = conn.execute(
                "INSERT INTO invoices (shop_id, uploaded_by, supplier_name, invoice_date, image_path, image_mime,"
                " status, extraction_source, extraction_error, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    user.shop_id, user.user_id,
                    extracted.supplier_name if extracted else "",
                    extracted.invoice_date if extracted else None,
                    image_rel, mime,
                    "review" if has_lines else "manual",
                    extractor.source if extracted else "manual",
                    error, now_iso(),
                ),
            ).lastrowid
            for position, line in enumerate(extracted.lines if extracted else [], start=1):
                match = match_line(line.name, line.unit, products, aliases)
                _insert_line(
                    conn, invoice_id, position, line.name, line.unit, line.qty, line.unit_cost_sen,
                    match.product_id, match.pack_size, match.status, match.score,
                )
            log_event(conn, user.shop_id, user.user_id, "invoice_uploaded", "invoice", invoice_id, {
                "source": extractor.source if extracted else "manual",
                "lines": len(extracted.lines) if extracted else 0,
                "extraction_error": error,
            })
    except BaseException:
        if image_file is not None:
            image_file.unlink(missing_ok=True)
        raise
    return invoice_id


def save_lines(
    conn: sqlite3.Connection,
    user: CurrentUser,
    invoice_id: int,
    lines: list[LineEdit],
    supplier_name: str | None = None,
) -> None:
    """Replace the invoice's lines with the reviewed ones. A product picked by a person is 'confirmed'."""
    with transaction(conn):
        invoice = get_invoice(conn, user.shop_id, invoice_id)
        if invoice is None:
            raise LookupError(invoice_id)
        if invoice["status"] == "proposed":
            raise InvoiceError("This invoice already has price proposals and can no longer be edited.")
        products, aliases = load_catalogue(conn, user.shop_id)
        shop_product_ids = {p.id for p in products}
        conn.execute("DELETE FROM invoice_lines WHERE invoice_id = ?", (invoice_id,))
        for edit in lines:
            match = match_line(edit.raw_name, edit.raw_unit, products, aliases)
            product_id, pack_size, status, score = match.product_id, match.pack_size, match.status, match.score
            if edit.product_id is not None:
                if edit.product_id not in shop_product_ids:
                    raise InvoiceError(f"Line {edit.position}: that product is not in your catalogue.")
                auto = match.status == "matched" and match.product_id == edit.product_id and match.pack_size == edit.pack_size
                product_id, pack_size, status = edit.product_id, edit.pack_size, "matched" if auto else "confirmed"
            if edit.skip:
                status = "skipped"
            _insert_line(
                conn, invoice_id, edit.position, edit.raw_name, edit.raw_unit, edit.qty, edit.unit_cost_sen,
                product_id, pack_size, status, score,
            )
        has_lines = any(not e.skip for e in lines)
        conn.execute(
            "UPDATE invoices SET status = ?, supplier_name = COALESCE(?, supplier_name) WHERE id = ?",
            ("review" if has_lines else "manual", supplier_name, invoice_id),
        )
        log_event(conn, user.shop_id, user.user_id, "invoice_reviewed", "invoice", invoice_id, {"lines": len(lines)})


def confirm_invoice(conn: sqlite3.Connection, user: CurrentUser, invoice_id: int, on: date) -> list[int]:
    """Turn every reviewed line into a price proposal. Checks and writes share one write transaction,
    so two confirms of the same invoice cannot both create proposals."""
    proposal_ids = []
    with transaction(conn):
        invoice = get_invoice(conn, user.shop_id, invoice_id)
        if invoice is None:
            raise LookupError(invoice_id)
        if invoice["status"] == "proposed":
            raise InvoiceError("This invoice already has price proposals.")
        lines = conn.execute(
            "SELECT l.*, p.name_bm FROM invoice_lines l LEFT JOIN products p ON p.id = l.product_id"
            " WHERE l.invoice_id = ? AND l.match_status != 'skipped' ORDER BY l.position",
            (invoice_id,),
        ).fetchall()
        if not lines:
            raise InvoiceError("There are no lines to price. Add the invoice lines first.")
        unresolved = [l for l in lines if l["match_status"] in UNRESOLVED or l["product_id"] is None]
        if unresolved:
            n = len(unresolved)
            raise InvoiceError(
                f"Resolve {n} line{'s' if n != 1 else ''} first: pick the catalogue product (and units per pack) or skip it."
            )
        seen: dict[int, int] = {}
        for line in lines:
            if line["product_id"] in seen:
                raise InvoiceError(
                    f"Lines {seen[line['product_id']]} and {line['position']} are the same product ({line['name_bm']}). "
                    "Merge them or skip one: a duplicate product cannot get two prices."
                )
            seen[line["product_id"]] = line["position"]

        limits = [limit_from_row(r) for r in conn.execute("SELECT * FROM price_limits")]
        for line in lines:
            product = conn.execute(
                "SELECT * FROM products WHERE id = ? AND shop_id = ?", (line["product_id"], user.shop_id)
            ).fetchone()
            new_cost = round_half_up_sen(Decimal(line["unit_cost_sen"]) / line["pack_size"])
            if new_cost <= 0:
                raise InvoiceError(
                    f"Line {line['position']} ({line['raw_name']}) costs RM 0.00 per {product['unit']}. "
                    "Skip free items: they cannot set a selling price."
                )
            code = product["controlled_item_code"]
            limit = (
                find_applicable_limit(limits, code, product["unit"], user.district, user.retail_level, on)
                if code else None
            )
            result = compute_proposal(ProposalInput(
                old_cost_sen=product["cost_sen"],
                new_cost_sen=new_cost,
                current_price_sen=product["price_sen"],
                target_margin=Decimal(product["target_margin"]),
                controlled=code is not None,
                limit=limit,
            ))
            proposal_ids.append(conn.execute(
                "INSERT INTO price_proposals (shop_id, invoice_id, invoice_line_id, product_id, base_version,"
                " old_cost_sen, new_cost_sen, old_price_sen, suggested_price_sen, cap_sen, limit_id,"
                " proposed_price_sen, flags, required_role, status, explanation, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    user.shop_id, invoice_id, line["id"], product["id"], product["version"],
                    product["cost_sen"], new_cost, product["price_sen"], result.suggested_price_sen,
                    result.cap_sen, limit.id if limit else None, result.proposed_price_sen,
                    json.dumps(result.flags), result.required_role, result.status,
                    json.dumps(result.explanation), now_iso(),
                ),
            ).lastrowid)
            alias_norm = normalize(line["raw_name"])
            if line["match_status"] == "confirmed" and alias_norm:
                conn.execute(
                    "INSERT INTO product_aliases (shop_id, product_id, alias_norm, unit_norm, pack_size)"
                    " VALUES (?, ?, ?, ?, ?) ON CONFLICT (shop_id, alias_norm, unit_norm)"
                    " DO UPDATE SET product_id = excluded.product_id, pack_size = excluded.pack_size",
                    (user.shop_id, product["id"], alias_norm, normalize(line["raw_unit"]), line["pack_size"]),
                )
        updated = conn.execute(
            "UPDATE invoices SET status = 'proposed' WHERE id = ? AND status != 'proposed'", (invoice_id,)
        ).rowcount
        if updated != 1:
            raise InvoiceError("This invoice already has price proposals.")
        log_event(conn, user.shop_id, user.user_id, "invoice_confirmed", "invoice", invoice_id, {
            "proposals": len(proposal_ids),
        })
    return proposal_ids
