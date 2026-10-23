"""Approval inbox: review proposals, approve, override or reject."""

import sqlite3

from fastapi import APIRouter, Depends, Form, HTTPException, Request

from .approvals import ApprovalError, approve_proposal, reject_proposal
from .auth import CurrentUser, current_user, get_db, require_roles, verify_csrf
from .money import MoneyError, format_rm, parse_rm, today_my
from .pricing import role_can_approve
from .web import flash, redirect, render

router = APIRouter()

PROPOSAL_QUERY = (
    "SELECT pp.*, p.name_bm, p.unit, p.sku, l.source_ref AS limit_source, l.verification AS limit_verification,"
    " u.display_name AS decided_by_name"
    " FROM price_proposals pp JOIN products p ON p.id = pp.product_id"
    " LEFT JOIN price_limits l ON l.id = pp.limit_id"
    " LEFT JOIN users u ON u.id = pp.decided_by"
    " WHERE pp.shop_id = ? AND {where} ORDER BY {order} LIMIT {limit}"
)


def _raise_for(exc: ApprovalError, request: Request, proposal_id: int):
    if exc.code == "not_found":
        raise HTTPException(status_code=404, detail=str(exc))
    if exc.code == "forbidden":
        raise HTTPException(status_code=403, detail=str(exc))
    flash(request, str(exc), "error")
    return redirect(f"/proposals#proposal-{proposal_id}")


@router.get("/proposals")
def proposals(request: Request, user: CurrentUser = Depends(current_user), conn: sqlite3.Connection = Depends(get_db)):
    open_rows = conn.execute(
        PROPOSAL_QUERY.format(where="pp.status IN ('pending', 'blocked')", order="pp.status DESC, pp.id", limit=200),
        (user.shop_id,),
    ).fetchall()
    decided = conn.execute(
        PROPOSAL_QUERY.format(where="pp.status IN ('approved', 'rejected', 'stale')", order="pp.decided_at DESC, pp.id DESC", limit=30),
        (user.shop_id,),
    ).fetchall()
    context = {
        "user": user,
        "open_rows": open_rows,
        "decided": decided,
        "can_approve": lambda row: row["status"] == "pending" and role_can_approve(user.role, row["required_role"]),
    }
    return render(request, "proposals.html", context)


@router.post("/proposals/{proposal_id}/approve")
def approve(
    request: Request,
    proposal_id: int,
    override_price: str = Form(""),
    note: str = Form(""),
    csrf_token: str = Form(""),
    user: CurrentUser = Depends(current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    verify_csrf(request, csrf_token)
    require_roles(user, "owner", "staff")
    override = None
    if override_price.strip():
        try:
            override = parse_rm(override_price)
        except MoneyError as exc:
            flash(request, str(exc), "error")
            return redirect(f"/proposals#proposal-{proposal_id}")
    try:
        final = approve_proposal(conn, user, proposal_id, override, note, today_my())
    except ApprovalError as exc:
        return _raise_for(exc, request, proposal_id)
    flash(request, f"Approved: new shelf price {format_rm(final)}. Print the tag from Print tags.", "success")
    return redirect("/proposals")


@router.post("/proposals/{proposal_id}/reject")
def reject(
    request: Request,
    proposal_id: int,
    note: str = Form(""),
    csrf_token: str = Form(""),
    user: CurrentUser = Depends(current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    verify_csrf(request, csrf_token)
    require_roles(user, "owner", "staff")
    try:
        reject_proposal(conn, user, proposal_id, note)
    except ApprovalError as exc:
        return _raise_for(exc, request, proposal_id)
    flash(request, "Rejected. The shelf price stays as it was.", "success")
    return redirect("/proposals")
