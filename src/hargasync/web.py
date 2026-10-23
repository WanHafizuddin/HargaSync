"""Template rendering and flash messages shared by all routers."""

import json
from pathlib import Path

from fastapi import Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from .auth import ensure_csrf
from .money import format_rm
from .pricing import DEMO_LABEL

PACKAGE_DIR = Path(__file__).resolve().parent

FLAG_LABELS = {
    "cost_jump": "Cost up over 15%",
    "below_cost": "Below cost",
    "controlled": "Price-controlled item",
    "capped": "Capped at ceiling",
    "demo_ceiling": DEMO_LABEL,
    "no_valid_ceiling": "No valid ceiling",
    "new_product": "First price",
    "large_change": "Change over 5%",
}


def _flashes(request: Request) -> list[dict]:
    return request.session.pop("flashes", [])


def _context(request: Request) -> dict:
    return {"csrf_token": ensure_csrf(request), "flashes": _flashes(request), "demo_label": DEMO_LABEL}


templates = Jinja2Templates(directory=str(PACKAGE_DIR / "templates"), context_processors=[_context])
templates.env.filters["rm"] = lambda sen: "—" if sen is None else format_rm(sen)
templates.env.filters["flag_label"] = lambda flag: FLAG_LABELS.get(flag, flag)
templates.env.filters["from_json"] = json.loads


def render(request: Request, name: str, context: dict | None = None, status_code: int = 200):
    return templates.TemplateResponse(request, name, context or {}, status_code=status_code)


def flash(request: Request, message: str, kind: str = "info") -> None:
    request.session.setdefault("flashes", []).append({"message": message, "kind": kind})


def redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)
