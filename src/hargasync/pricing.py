"""Deterministic pricing rules. No AI here: every number is reproducible from the inputs."""

from dataclasses import dataclass, field
from decimal import Decimal

from .limits import PriceLimit
from .money import format_rm, price_from_margin

COST_JUMP_PERCENT = 15  # flag supplier cost increases over this
STAFF_MAX_CHANGE_PERCENT = 5  # staff may approve changes up to this share of the current price
DEMO_LABEL = "DEMO — fictional ceiling"


@dataclass(frozen=True)
class ProposalInput:
    old_cost_sen: int
    new_cost_sen: int
    current_price_sen: int | None
    target_margin: Decimal
    controlled: bool
    limit: PriceLimit | None


@dataclass
class ProposalResult:
    suggested_price_sen: int
    cap_sen: int | None
    proposed_price_sen: int | None
    flags: list[str] = field(default_factory=list)
    required_role: str = "owner"
    status: str = "pending"
    explanation: list[str] = field(default_factory=list)


def _percent(margin: Decimal) -> str:
    return f"{(margin * 100).normalize():f}%"


def compute_proposal(inp: ProposalInput) -> ProposalResult:
    flags: list[str] = []
    explanation: list[str] = []

    if inp.old_cost_sen > 0:
        change = Decimal(inp.new_cost_sen - inp.old_cost_sen) * 100 / inp.old_cost_sen
        explanation.append(
            f"Supplier cost {format_rm(inp.old_cost_sen)} → {format_rm(inp.new_cost_sen)} ({change:+.1f}%)."
        )
        if (inp.new_cost_sen - inp.old_cost_sen) * 100 > inp.old_cost_sen * COST_JUMP_PERCENT:
            flags.append("cost_jump")
            explanation.append(f"Cost rose more than {COST_JUMP_PERCENT}% — check the invoice before approving.")
    else:
        explanation.append(f"Supplier cost {format_rm(inp.new_cost_sen)} (no previous cost).")

    suggested = price_from_margin(inp.new_cost_sen, inp.target_margin)
    explanation.append(
        f"Target price = {format_rm(inp.new_cost_sen)} ÷ (1 − {_percent(inp.target_margin)}) "
        f"= {format_rm(suggested)} (rounded up to RM0.10)."
    )

    cap = None
    proposed: int | None = suggested
    status = "pending"
    if inp.controlled:
        flags.append("controlled")
        if inp.limit is None:
            flags.append("no_valid_ceiling")
            status = "blocked"
            proposed = None
            explanation.append(
                "Controlled item: no valid ceiling found for this item, unit, district and date. "
                "Price cannot change until a valid, dated source is recorded."
            )
        else:
            cap = inp.limit.max_price_sen
            source = inp.limit.source_ref
            if inp.limit.verification == "demo":
                flags.append("demo_ceiling")
                source = f"{DEMO_LABEL} ({source})"
            explanation.append(
                f"Ceiling {format_rm(cap)} per {inp.limit.unit} in {inp.limit.district} ({inp.limit.retail_level}), "
                f"valid {inp.limit.valid_from:%d/%m/%Y}–{inp.limit.valid_to:%d/%m/%Y}. Source: {source}."
            )
            if suggested > cap:
                flags.append("capped")
                proposed = cap
                explanation.append(f"Capped from {format_rm(suggested)} to {format_rm(cap)}.")

    if proposed is not None and proposed < inp.new_cost_sen:
        flags.append("below_cost")
        explanation.append(f"Proposed price {format_rm(proposed)} is below cost {format_rm(inp.new_cost_sen)}.")

    if inp.current_price_sen is None:
        flags.append("new_product")
        explanation.append("No current selling price — first price needs the owner.")
    elif proposed is not None:
        delta = abs(proposed - inp.current_price_sen)
        if delta * 100 > inp.current_price_sen * STAFF_MAX_CHANGE_PERCENT:
            flags.append("large_change")
            explanation.append(
                f"Change from {format_rm(inp.current_price_sen)} is more than {STAFF_MAX_CHANGE_PERCENT}% of the current price."
            )

    required_role = "owner" if flags else "staff"
    explanation.append(
        "Staff may approve: non-controlled change within 5% with no warnings."
        if required_role == "staff"
        else "Owner approval required."
    )
    return ProposalResult(
        suggested_price_sen=suggested,
        cap_sen=cap,
        proposed_price_sen=proposed,
        flags=flags,
        required_role=required_role,
        status=status,
        explanation=explanation,
    )


def role_can_approve(role: str, required_role: str) -> bool:
    if role == "owner":
        return True
    return role == "staff" and required_role == "staff"
