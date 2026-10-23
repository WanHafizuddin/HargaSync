# HargaSync MVP — Design

Source: `HargaSync_Project_Summary.pdf` (team summary, 23 Oct 2026) plus an audit of the
official SDC 2026 submission template (this repository's starting commit).

## Intent

Malaysian micro-retailers (kedai runcit, mini-markets) receive supplier invoices whose costs
change often. Changing a supplier cost is not the same as changing a shelf price: the shop must
match the item, keep its margin, respect any regulated price ceiling and replace the shelf label.
HargaSync turns one supplier invoice photo into reviewable price proposals, an authorised
catalogue update and a print-ready Bahasa Malaysia shelf-label sheet, with an audit trail.

Flow: **Invoice → AI reads → price rules → approve → print tags.**

Users:

| Role | Can do |
|------|--------|
| Owner (pemilik) | Everything; final approval, price overrides, add products |
| Staff (pekerja) | Upload invoices, resolve lines, approve eligible minor non-controlled changes, print tags |
| Auditor | Read-only: proposals, activity, catalogue |

## Constraints forced by the template

- Replit is the required dev/hosting platform (`.replit` runs `python src/main.py`).
- RunPod is the required AI compute: `runpod/handler.py` is a RunPod Serverless endpoint.
- Template language is Python; tests run with `unittest`.
- The README's sections (Replit use, RunPod use, submission checklist) must be filled in.

## Decisions

- Python 3.11-compatible code (Replit `python-3.11` module), FastAPI, Jinja2 server-rendered
  pages, SQLite via the standard library. No front-end build step.
- Money is integer sen; arithmetic uses `Decimal`; never floats.
- AI = an open vision-language model (`Qwen/Qwen2.5-VL-7B-Instruct` by default, configurable)
  running in the RunPod handler. It returns invoice JSON only.
- An AI adapter with three modes: `runpod`, `fixture` (canned, clearly labelled "Simulated AI")
  and `off`. Manual line entry always works.

## Pricing rules (from the summary, verbatim values)

- Target selling price = cost / (1 − target margin), rounded **up** to RM0.10.
- Verified ceiling: cap an applicable controlled item at the maximum for the exact item, unit,
  district, retail level and date. Missing or expired evidence = review required.
- Exceptions: flag supplier cost increases **over 15%**, uncertain SKU/unit matches and
  below-cost outcomes.
- Routing: staff may approve eligible non-controlled changes **up to 5%** of the current
  selling price; all other sensitive cases route to the owner.
- Traceability: show the calculation, applicable source, reason, approver and final price.
- Safety: AI only reads and helps match documents. It never decides legal ceilings, approves
  prices or edits the catalogue. Unverified demo ceilings are marked fictional. An owner cannot
  self-certify a demo fixture.

## Security and integrity

- Shop isolation and role checks are enforced on the server for every read and write.
- Supplier invoices are stored outside any static folder and served only to the owning shop.
- Secrets stay server-side; uploaded files and AI JSON are validated.
- Approval re-checks rules, actor and catalogue version, then updates price and writes the audit
  event in one transaction. Repeated or stale approvals write nothing.
- Audit log is append-only (database triggers block UPDATE/DELETE).

## Goals

Pages: Overview, Review invoice, Price proposals / approval inbox, Print tags, Activity,
Catalogue, Login. Acceptance scenarios from the summary (input & AI, price math, regulation,
access control, data consistency, output & recovery) are covered by automated tests.

## Non-goals

Full ERP, stock, accounting, payments, tax, HR, forecasting; real WhatsApp ingestion; real
POS/Orbyte integration; live government price feed; legal certification; autonomous AI approval.

## Anti-goals

- A price published above an applicable ceiling, or a demo ceiling presented as official.
- Staff able to approve owner-only changes because of a UI-only check.
- A printed tag that differs from the approved catalogue price.

## Calls made by the builder (not decided by the team)

- Controlled item with **no valid ceiling** → proposal is `blocked`: nobody can approve a new
  price until valid evidence exists; owner may reject.
- **Demo** ceilings are applied as caps (capping only lowers price) but the proposal requires the
  owner and every screen and tag shows "DEMO — fictional ceiling".
- Several applicable ceilings → the lowest one is used.
- New product (no current price), cost jump, below-cost, uncertain match or a demo ceiling →
  owner. Change exactly 5.00% → staff may approve; exactly 15.00% cost increase → not flagged.
- Owner override must stay at or below the cap and needs a reason; staff cannot override.
- Supplier stored as a name on the invoice (no separate suppliers table).
- One shop per user in the MVP.
- Confirmed unit/pack mappings are saved as aliases so the next invoice matches automatically.
- SQLite on Replit is reset on redeploy; demo data auto-seeds on an empty database.
