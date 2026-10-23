"""Printable shelf tags, the activity log and the catalogue."""

import sqlite3
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Form, Query, Request

from .audit import list_events, log_event
from .auth import CurrentUser, current_user, get_db, require_roles, verify_csrf
from .db import transaction
from .limits import find_applicable_limit, limit_from_row
from .money import MoneyError, format_rm, parse_rm, today_my
from .web import flash, redirect, render

router = APIRouter()
TAGS_PER_SHEET = 24
RECENT_DAYS = 7


def _last_approvals(conn: sqlite3.Connection, shop_id: int) -> dict[int, str]:
    rows = conn.execute(
        "SELECT product_id, MAX(decided_at) AS decided_at FROM price_proposals"
        " WHERE shop_id = ? AND status = 'approved' GROUP BY product_id",
        (shop_id,),
    ).fetchall()
    return {r["product_id"]: r["decided_at"] for r in rows}


@router.get("/tags")
def tags(request: Request, user: CurrentUser = Depends(current_user), conn: sqlite3.Connection = Depends(get_db)):
    products = conn.execute(
        "SELECT * FROM products WHERE shop_id = ? ORDER BY name_bm", (user.shop_id,)
    ).fetchall()
    approvals = _last_approvals(conn, user.shop_id)
    cutoff = (datetime.fromisoformat(f"{today_my()}T00:00:00") - timedelta(days=RECENT_DAYS)).date().isoformat()
    recent = {pid for pid, decided in approvals.items() if decided[:10] >= cutoff}
    context = {"user": user, "products": products, "approvals": approvals, "recent": recent}
    return render(request, "tags.html", context)


@router.get("/tags/print")
def print_tags(
    request: Request,
    ids: list[int] = Query(default=[]),
    user: CurrentUser = Depends(current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    wanted = list(dict.fromkeys(ids))[:240]
    rows = []
    if wanted:
        marks = ",".join("?" * len(wanted))
        rows = conn.execute(
            f"SELECT * FROM products WHERE shop_id = ? AND id IN ({marks}) ORDER BY name_bm",
            (user.shop_id, *wanted),
        ).fetchall()
    approvals = _last_approvals(conn, user.shop_id)
    limits = [limit_from_row(r) for r in conn.execute("SELECT * FROM price_limits")]
    today = today_my()
    labels, held = [], []
    for product in rows:
        if product["price_sen"] is None:
            held.append((product, "no approved price yet"))
            continue
        code = product["controlled_item_code"]
        limit = find_applicable_limit(limits, code, product["unit"], user.district, user.retail_level, today) if code else None
        if code and limit is None:
            held.append((product, "price-controlled, and no valid ceiling today, so the price cannot be confirmed"))
            continue
        if limit is not None and product["price_sen"] > limit.max_price_sen:
            held.append((product, f"{format_rm(product['price_sen'])} is above the ceiling of {format_rm(limit.max_price_sen)}"))
            continue
        decided = approvals.get(product["id"])
        labels.append({
            "product": product,
            "controlled": code is not None,
            "demo": limit is not None and limit.verification == "demo",
            "effective": date.fromisoformat(decided[:10]) if decided else today,
        })
    sheets = [labels[i : i + TAGS_PER_SHEET] for i in range(0, len(labels), TAGS_PER_SHEET)]
    return render(request, "tags_print.html", {"user": user, "sheets": sheets, "held": held, "count": len(labels)})


@router.get("/activity")
def activity(request: Request, user: CurrentUser = Depends(current_user), conn: sqlite3.Connection = Depends(get_db)):
    return render(request, "activity.html", {"user": user, "events": list_events(conn, user.shop_id)})


def _catalogue_context(conn, user, **extra) -> dict:
    products = conn.execute("SELECT * FROM products WHERE shop_id = ? ORDER BY name_bm", (user.shop_id,)).fetchall()
    codes = [r["item_code"] for r in conn.execute("SELECT DISTINCT item_code FROM price_limits ORDER BY item_code")]
    return {"user": user, "products": products, "codes": codes, "form": {}, "error": None, **extra}


@router.get("/catalogue")
def catalogue(request: Request, user: CurrentUser = Depends(current_user), conn: sqlite3.Connection = Depends(get_db)):
    return render(request, "catalogue.html", _catalogue_context(conn, user))


def _parse_product(sku, name_bm, unit, cost, price, margin, code) -> tuple:
    sku, name_bm, unit = sku.strip().upper(), name_bm.strip(), unit.strip()
    if not sku or len(sku) > 40 or not name_bm or len(name_bm) > 120 or not unit or len(unit) > 30:
        raise ValueError("Fill in SKU (up to 40 characters), BM name (up to 120) and unit (up to 30).")
    try:
        cost_sen = parse_rm(cost)
        price_sen = parse_rm(price) if price.strip() else None
    except MoneyError as exc:
        raise ValueError(str(exc)) from None
    if price_sen == 0:
        raise ValueError("Leave the price empty if the product has none yet; it cannot be RM 0.00.")
    try:
        margin_value = Decimal(margin.strip()) / 100
    except InvalidOperation:
        raise ValueError("Target margin must be a percentage, e.g. 15.") from None
    if not margin_value.is_finite() or not 0 <= margin_value < Decimal("0.9"):
        raise ValueError("Target margin must be between 0% and 90%.")
    return sku, name_bm, unit, cost_sen, price_sen, str(margin_value.normalize()), code.strip() or None


def _check_ceiling(conn, user: CurrentUser, unit: str, price_sen: int | None, code: str | None) -> None:
    """A controlled product may only start with a price that a valid ceiling allows."""
    if not code or price_sen is None:
        return
    limits = [limit_from_row(r) for r in conn.execute("SELECT * FROM price_limits WHERE item_code = ?", (code,))]
    limit = find_applicable_limit(limits, code, unit, user.district, user.retail_level, today_my())
    if limit is None:
        raise ValueError(
            f"No valid ceiling for {code} per {unit} in {user.district} today. "
            "Leave the shelf price empty: the first price will go through approval."
        )
    if price_sen > limit.max_price_sen:
        raise ValueError(f"{format_rm(price_sen)} is above the ceiling of {format_rm(limit.max_price_sen)} for {code} per {unit}.")


@router.post("/catalogue")
def add_product(
    request: Request,
    sku: str = Form(""),
    name_bm: str = Form(""),
    unit: str = Form(""),
    cost: str = Form(""),
    price: str = Form(""),
    margin: str = Form(""),
    controlled_item_code: str = Form(""),
    csrf_token: str = Form(""),
    user: CurrentUser = Depends(current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    verify_csrf(request, csrf_token)
    require_roles(user, "owner")
    form = {"sku": sku, "name_bm": name_bm, "unit": unit, "cost": cost, "price": price, "margin": margin,
            "controlled_item_code": controlled_item_code}
    try:
        values = _parse_product(sku, name_bm, unit, cost, price, margin, controlled_item_code)
        _check_ceiling(conn, user, unit=values[2], price_sen=values[4], code=values[6])
        with transaction(conn):
            product_id = conn.execute(
                "INSERT INTO products (shop_id, sku, name_bm, unit, cost_sen, price_sen, target_margin,"
                " controlled_item_code) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (user.shop_id, *values),
            ).lastrowid
            log_event(conn, user.shop_id, user.user_id, "product_added", "product", product_id, {
                "product": values[1], "sku": values[0], "price_sen": values[4],
            })
    except ValueError as exc:
        return render(request, "catalogue.html", _catalogue_context(conn, user, form=form, error=str(exc)), status_code=400)
    except sqlite3.IntegrityError:
        error = f"SKU {values[0]} is already used in your catalogue."
        return render(request, "catalogue.html", _catalogue_context(conn, user, form=form, error=error), status_code=400)
    flash(request, f"Added {values[1]}.", "success")
    return redirect("/catalogue")
