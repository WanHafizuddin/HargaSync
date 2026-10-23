"""Overview, invoice upload and the review screen."""

import sqlite3
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from .auth import CurrentUser, current_user, get_db, require_roles, verify_csrf
from .extraction import FIXTURE_PATH, MAX_QTY
from .invoices import (
    MAX_UPLOAD_BYTES,
    InvoiceError,
    LineEdit,
    UploadError,
    confirm_invoice,
    create_invoice,
    get_invoice,
    save_lines,
)
from .money import MoneyError, parse_rm, today_my
from .web import flash, redirect, render

router = APIRouter()
EDITORS = ("owner", "staff")


def overview_context(request: Request, conn: sqlite3.Connection, user: CurrentUser) -> dict:
    pending = conn.execute(
        "SELECT required_role, COUNT(*) AS n FROM price_proposals"
        " WHERE shop_id = ? AND status = 'pending' GROUP BY required_role",
        (user.shop_id,),
    ).fetchall()
    invoices = conn.execute(
        "SELECT i.*, (SELECT COUNT(*) FROM invoice_lines l WHERE l.invoice_id = i.id) AS line_count"
        " FROM invoices i WHERE i.shop_id = ? ORDER BY i.id DESC LIMIT 10",
        (user.shop_id,),
    ).fetchall()
    return {
        "user": user,
        "pending": {row["required_role"]: row["n"] for row in pending},
        "invoices": invoices,
        "ai_source": request.app.state.extractor.source,
    }


def _invoice_or_404(conn, user, invoice_id):
    invoice = get_invoice(conn, user.shop_id, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found.")
    return invoice


@router.get("/")
def overview(request: Request, user: CurrentUser = Depends(current_user), conn: sqlite3.Connection = Depends(get_db)):
    return render(request, "overview.html", overview_context(request, conn, user))


@router.get("/sample-invoice")
def sample_invoice(user: CurrentUser = Depends(current_user)):
    """The fictional demo invoice photo, so judges can try the upload."""
    return FileResponse(FIXTURE_PATH.with_suffix(".png"), media_type="image/png", filename="sample_invoice.png")


@router.post("/invoices")
async def upload_invoice(
    request: Request,
    photo: UploadFile | None = File(None),
    manual: str = Form(""),
    csrf_token: str = Form(""),
    user: CurrentUser = Depends(current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    verify_csrf(request, csrf_token)
    require_roles(user, *EDITORS)
    image = None
    if not manual:
        image = await photo.read(MAX_UPLOAD_BYTES + 1) if photo is not None else b""
    try:
        invoice_id = create_invoice(conn, user, image, request.app.state.extractor, request.app.state.settings.data_dir)
    except UploadError as exc:
        context = overview_context(request, conn, user)
        context["upload_error"] = str(exc)
        return render(request, "overview.html", context, status_code=400)
    return redirect(f"/invoices/{invoice_id}")


@router.get("/invoices/{invoice_id}")
def review_invoice(
    request: Request,
    invoice_id: int,
    user: CurrentUser = Depends(current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    invoice = _invoice_or_404(conn, user, invoice_id)
    lines = conn.execute(
        "SELECT l.*, p.name_bm AS product_name, p.unit AS product_unit FROM invoice_lines l"
        " LEFT JOIN products p ON p.id = l.product_id WHERE l.invoice_id = ? ORDER BY l.position",
        (invoice_id,),
    ).fetchall()
    products = conn.execute(
        "SELECT id, sku, name_bm, unit FROM products WHERE shop_id = ? ORDER BY name_bm", (user.shop_id,)
    ).fetchall()
    context = {
        "user": user,
        "invoice": invoice,
        "lines": lines,
        "products": products,
        "can_edit": user.role in EDITORS and invoice["status"] != "proposed",
    }
    return render(request, "review.html", context)


@router.get("/invoices/{invoice_id}/image")
def invoice_image(
    request: Request,
    invoice_id: int,
    user: CurrentUser = Depends(current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    invoice = _invoice_or_404(conn, user, invoice_id)
    if not invoice["image_path"]:
        raise HTTPException(status_code=404, detail="This invoice has no photo.")
    path = request.app.state.settings.data_dir / invoice["image_path"]
    if not path.is_file():
        raise HTTPException(status_code=404, detail="The photo file is missing.")
    return FileResponse(path, media_type=invoice["image_mime"], headers={"Cache-Control": "private, no-store"})


def _parse_lines(form) -> list[LineEdit]:
    """Read the review table. Blank rows are dropped; any bad value raises InvoiceError naming the line."""
    try:
        count = int(form.get("line_count", "0"))
    except ValueError:
        raise InvoiceError("The form was incomplete. Reload the page and try again.") from None
    edits = []
    for i in range(1, min(count, 200) + 2):  # +1 for the blank "add a line" row
        name = (form.get(f"name_{i}") or "").strip()
        cost_text = (form.get(f"cost_{i}") or "").strip()
        if not name and not cost_text:
            continue
        label = f"Line {len(edits) + 1}"
        if not name or len(name) > 120:
            raise InvoiceError(f"{label}: enter the product name (up to 120 characters).")
        unit = (form.get(f"unit_{i}") or "").strip()[:30]
        try:
            qty = Decimal((form.get(f"qty_{i}") or "").strip())
        except InvalidOperation:
            qty = Decimal(0)
        if not qty.is_finite() or qty <= 0 or qty > MAX_QTY:
            raise InvoiceError(f"{label}: quantity must be a number above 0.")
        try:
            cost = parse_rm(cost_text)
        except MoneyError:
            raise InvoiceError(f"{label}: unit cost {cost_text!r} is not a ringgit amount. Use a dot, e.g. 12.50.") from None
        product_text = (form.get(f"product_{i}") or "").strip()
        try:
            product_id = int(product_text) if product_text else None
            pack = int((form.get(f"pack_{i}") or "1").strip())
        except ValueError:
            raise InvoiceError(f"{label}: units per pack must be a whole number.") from None
        if not 1 <= pack <= 1000:
            raise InvoiceError(f"{label}: units per pack must be between 1 and 1000.")
        edits.append(LineEdit(len(edits) + 1, name, unit, qty, cost, product_id, pack, bool(form.get(f"skip_{i}"))))
    return edits


@router.post("/invoices/{invoice_id}/lines")
async def save_invoice_lines(
    request: Request,
    invoice_id: int,
    user: CurrentUser = Depends(current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    form = await request.form()
    verify_csrf(request, form.get("csrf_token", ""))
    require_roles(user, *EDITORS)
    _invoice_or_404(conn, user, invoice_id)
    try:
        save_lines(conn, user, invoice_id, _parse_lines(form), supplier_name=(form.get("supplier_name") or None))
        if form.get("action") == "confirm":
            ids = confirm_invoice(conn, user, invoice_id, today_my())
            flash(request, f"Created {len(ids)} price proposal{'s' if len(ids) != 1 else ''} from invoice #{invoice_id}.", "success")
            return redirect("/proposals")
        flash(request, "Changes saved.", "success")
    except InvoiceError as exc:
        flash(request, str(exc), "error")
    return redirect(f"/invoices/{invoice_id}")


@router.post("/invoices/{invoice_id}/confirm")
def confirm(
    request: Request,
    invoice_id: int,
    csrf_token: str = Form(""),
    user: CurrentUser = Depends(current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    verify_csrf(request, csrf_token)
    _invoice_or_404(conn, user, invoice_id)
    require_roles(user, *EDITORS)
    try:
        ids = confirm_invoice(conn, user, invoice_id, today_my())
    except InvoiceError as exc:
        flash(request, str(exc), "error")
        return redirect(f"/invoices/{invoice_id}")
    flash(request, f"Created {len(ids)} price proposal{'s' if len(ids) != 1 else ''} from invoice #{invoice_id}.", "success")
    return redirect("/proposals")
