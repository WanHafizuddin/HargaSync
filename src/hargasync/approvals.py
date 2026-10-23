"""Approving or rejecting a price proposal. Every check is redone inside one write transaction."""

import sqlite3
from datetime import date
from decimal import Decimal

from .audit import log_event
from .auth import CurrentUser
from .db import now_iso, transaction
from .limits import find_applicable_limit, limit_from_row
from .money import format_rm
from .pricing import DEMO_LABEL, ProposalInput, compute_proposal, role_can_approve


class ApprovalError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _load_proposal(conn: sqlite3.Connection, user: CurrentUser, proposal_id: int) -> sqlite3.Row:
    proposal = conn.execute(
        "SELECT * FROM price_proposals WHERE id = ? AND shop_id = ?", (proposal_id, user.shop_id)
    ).fetchone()
    if proposal is None:
        raise ApprovalError("not_found", "Proposal not found.")
    return proposal


def _recompute(conn, user: CurrentUser, proposal, product, on: date):
    code = product["controlled_item_code"]
    limit = None
    if code:
        limits = [limit_from_row(r) for r in conn.execute("SELECT * FROM price_limits WHERE item_code = ?", (code,))]
        limit = find_applicable_limit(limits, code, product["unit"], user.district, user.retail_level, on)
    result = compute_proposal(ProposalInput(
        old_cost_sen=product["cost_sen"],
        new_cost_sen=proposal["new_cost_sen"],
        current_price_sen=product["price_sen"],
        target_margin=Decimal(product["target_margin"]),
        controlled=code is not None,
        limit=limit,
    ))
    return result, limit


def _apply_approval(conn, user, proposal, product, override_price_sen, note, on) -> int:
    result, limit = _recompute(conn, user, proposal, product, on)
    if result.status == "blocked":
        raise ApprovalError("blocked", "No valid ceiling for this controlled item today, so its price cannot change.")
    if not role_can_approve(user.role, result.required_role):
        raise ApprovalError("forbidden", "This change needs the owner's approval.")
    final = result.proposed_price_sen
    if override_price_sen is not None:
        if user.role != "owner":
            raise ApprovalError("forbidden", "Only the owner can change the proposed price.")
        if not note:
            raise ApprovalError("needs_reason", "Write a reason when you change the proposed price.")
        if override_price_sen <= 0:
            raise ApprovalError("bad_price", "The price must be above RM 0.00.")
        if result.cap_sen is not None and override_price_sen > result.cap_sen:
            raise ApprovalError(
                "over_cap", f"{format_rm(override_price_sen)} is above the ceiling of {format_rm(result.cap_sen)}."
            )
        final = override_price_sen

    updated = conn.execute(
        "UPDATE products SET cost_sen = ?, price_sen = ?, version = version + 1 WHERE id = ? AND version = ?",
        (proposal["new_cost_sen"], final, product["id"], proposal["base_version"]),
    ).rowcount
    decided = conn.execute(
        "UPDATE price_proposals SET status = 'approved', decided_by = ?, decided_at = ?, final_price_sen = ?,"
        " decision_note = ? WHERE id = ? AND status = 'pending'",
        (user.user_id, now_iso(), final, note or None, proposal["id"]),
    ).rowcount
    if updated != 1 or decided != 1:
        raise ApprovalError("stale", "The catalogue changed while you were approving. Reload and check again.")
    log_event(conn, user.shop_id, user.user_id, "price_approved", "product", product["id"], {
        "proposal_id": proposal["id"],
        "product": product["name_bm"],
        "sku": product["sku"],
        "old_price_sen": product["price_sen"],
        "new_price_sen": final,
        "old_cost_sen": product["cost_sen"],
        "new_cost_sen": proposal["new_cost_sen"],
        "cap_sen": result.cap_sen,
        "ceiling_source": (f"{DEMO_LABEL} ({limit.source_ref})" if limit.verification == "demo" else limit.source_ref)
        if limit else None,
        "override": override_price_sen is not None,
        "note": note or None,
        "approver_role": user.role,
        "required_role": result.required_role,
    })
    return final


def approve_proposal(
    conn: sqlite3.Connection,
    user: CurrentUser,
    proposal_id: int,
    override_price_sen: int | None,
    note: str,
    on: date,
) -> int:
    """Re-check rules, role and catalogue version, then update price and log it atomically."""
    note = (note or "").strip()[:500]
    stale = False
    with transaction(conn):
        proposal = _load_proposal(conn, user, proposal_id)
        if proposal["status"] == "blocked":
            raise ApprovalError("blocked", "No valid ceiling for this controlled item, so its price cannot change.")
        if proposal["status"] != "pending":
            raise ApprovalError("already_decided", f"This proposal was already {proposal['status']}.")
        product = conn.execute(
            "SELECT * FROM products WHERE id = ? AND shop_id = ?", (proposal["product_id"], user.shop_id)
        ).fetchone()
        if product["version"] != proposal["base_version"]:
            conn.execute(
                "UPDATE price_proposals SET status = 'stale', decided_at = ? WHERE id = ? AND status = 'pending'",
                (now_iso(), proposal_id),
            )
            log_event(conn, user.shop_id, user.user_id, "proposal_stale", "proposal", proposal_id, {
                "product": product["name_bm"], "base_version": proposal["base_version"], "current_version": product["version"],
            })
            stale = True
        else:
            final = _apply_approval(conn, user, proposal, product, override_price_sen, note, on)
    if stale:
        raise ApprovalError(
            "stale", "The catalogue changed since this proposal was made (another price was approved). It is now stale."
        )
    return final


def reject_proposal(conn: sqlite3.Connection, user: CurrentUser, proposal_id: int, note: str) -> None:
    note = (note or "").strip()[:500]
    with transaction(conn):
        proposal = _load_proposal(conn, user, proposal_id)
        if proposal["status"] not in ("pending", "blocked"):
            raise ApprovalError("already_decided", f"This proposal was already {proposal['status']}.")
        allowed = user.role == "owner" or (
            user.role == "staff" and proposal["status"] == "pending" and proposal["required_role"] == "staff"
        )
        if not allowed:
            raise ApprovalError("forbidden", "Only the owner can reject this proposal.")
        conn.execute(
            "UPDATE price_proposals SET status = 'rejected', decided_by = ?, decided_at = ?, decision_note = ?"
            " WHERE id = ?",
            (user.user_id, now_iso(), note or None, proposal_id),
        )
        log_event(conn, user.shop_id, user.user_id, "price_rejected", "proposal", proposal_id, {
            "product_id": proposal["product_id"], "proposed_price_sen": proposal["proposed_price_sen"], "note": note or None,
        })
