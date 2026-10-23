# HargaSync MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A working web MVP where a shop uploads a supplier invoice photo, AI extracts the lines, deterministic rules propose capped selling prices, an authorised user approves them atomically and BM shelf tags print from the approved catalogue.

**Architecture:** FastAPI app in `src/hargasync/` with server-rendered Jinja2 pages and SQLite. Pure modules (`money`, `pricing`, `limits`, `matching`) hold all rules and are tested without a server; service modules (`invoices`, `approvals`, `audit`) own every write; routes only parse input, check the session and call services. Invoice reading goes through an adapter whose production backend is the RunPod handler in `runpod/handler.py`.

**Tech Stack:** Python 3.11+, FastAPI, Uvicorn, Jinja2, python-multipart, itsdangerous (sessions), httpx, Pillow, SQLite (stdlib), unittest. RunPod handler: runpod, torch, transformers, Qwen2.5-VL.

**Spec:** `docs/superpowers/specs/2026-10-23-hargasync-mvp-design.md`

## Global Constraints

- Code must run on Python 3.11 (Replit `python-3.11` module); no 3.12-only syntax.
- Money stored as integer sen; computed with `Decimal`; floats never touch money.
- Target price = cost / (1 − margin), rounded **up** to the next 10 sen.
- Cost increase flag: increase **> 15%** of old cost (exactly 15% is not flagged).
- Staff may approve only when change ≤ **5%** of current price, item not controlled, no flags.
- Every DB read/write is scoped by the session user's `shop_id`; another shop's id returns 404.
- Every state-changing POST requires the session CSRF token (403 otherwise).
- Demo ceilings show the exact text `DEMO — fictional ceiling`; the "Simulated AI" label shows when the fixture extractor is used.
- Run tests with `python -m unittest discover -s tests -t .`.
- Malaysia time is fixed UTC+8 (`timezone(timedelta(hours=8))`); no tzdata dependency.

## Review Focus

1. Non-image or oversize upload (> 8 MB) → 400 with a message, nothing written to disk or DB. (Task 7)
2. AI JSON with zero/negative quantity, negative cost or > 100 lines → extraction rejected, invoice opens in manual mode. (Task 5)
3. Same product on two lines of one invoice → confirm refuses with "duplicate product" instead of creating two proposals. (Task 7)
4. Price typed as `RM12.50`, `12.5` or ` 12.50 ` parses to 1250 sen; `12,50`, `abc`, `-1` are rejected with a message. (Task 1)
5. RunPod cold start: `runsync` returns `IN_QUEUE` → client polls `/status/{id}` until COMPLETED or timeout, then falls back to manual. (Task 5)

---

### Task 1: Skeleton, settings, money

**Files:**
- Modify: `requirements.txt`, `.env.example`, `.gitignore`, `.replit`, `src/main.py`
- Delete: `src/utils.py`, `tests/test_utils.py`
- Create: `src/hargasync/__init__.py`, `src/hargasync/config.py`, `src/hargasync/money.py`, `tests/__init__.py` (inserts `src` into `sys.path`), `tests/test_money.py`

**Interfaces:**
- Produces: `Settings` (frozen dataclass: `data_dir: Path`, `secret_key: str`, `ai_mode: str` in `{"runpod","fixture","off"}`, `runpod_api_key: str`, `runpod_endpoint_id: str`, `demo_seed: bool`, `demo_password: str`, `https_only: bool`), `load_settings() -> Settings` (env vars `HARGASYNC_DATA_DIR`, `HARGASYNC_SECRET_KEY`, `AI_MODE`, `RUNPOD_API_KEY`, `RUNPOD_ENDPOINT_ID`, `DEMO_SEED`, `DEMO_PASSWORD`, `HTTPS_ONLY`; missing secret → random per-process key plus a printed warning).
- Produces: `parse_rm(text: str) -> int`, `format_rm(sen: int) -> str` (`"RM 12.30"`), `round_up_10_sen(value: Decimal) -> int`, `price_from_margin(cost_sen: int, margin: Decimal) -> int`, `MoneyError(ValueError)`, `MY_TZ`, `today_my() -> date`.
- `src/main.py`: runs `uvicorn` on `0.0.0.0:$PORT` (default 8000) with `create_app()` from Task 6.

- [ ] **Step 1: Write failing tests** in `tests/test_money.py`:
  `price_from_margin(1000, Decimal("0.20")) == 1250`; `price_from_margin(1003, Decimal("0.25")) == 1340`; `price_from_margin(1170, Decimal("0.10")) == 1300`; `round_up_10_sen(Decimal("1250")) == 1250`; `round_up_10_sen(Decimal("1250.0001")) == 1260`; `parse_rm("RM12.50") == parse_rm("12.5") == parse_rm(" 12.50 ") == 1250`; `parse_rm` raises `MoneyError` for `"12,50"`, `"abc"`, `"-1"`, `"1.234"`; `format_rm(1230) == "RM 12.30"`; `price_from_margin(1000, Decimal("0")) == 1000`; `price_from_margin` raises `MoneyError` for margin `1` and `-0.01`.
- [ ] **Step 2:** `python -m unittest tests.test_money -v` → FAIL (module missing).
- [ ] **Step 3:** Implement `money.py`, `config.py`; update `requirements.txt` (pinned app deps; `runpod` moves to `runpod/requirements.txt`), `.env.example` (all vars above with demo values), `.gitignore` (+ `data/`), `.replit` (`modules = ["python-3.11"]`, run command, port 8000→80, deployment run).
- [ ] **Step 4:** Run tests → PASS.
- [ ] **Step 5:** Commit `feat: add settings and money helpers`.

### Task 2: Database schema and append-only audit

**Files:**
- Create: `src/hargasync/schema.sql`, `src/hargasync/db.py`, `src/hargasync/audit.py`, `tests/test_db.py`

**Interfaces:**
- Produces: `connect(path: Path) -> sqlite3.Connection` (`Row` factory, `foreign_keys=ON`, `isolation_level=None`), `init_db(conn) -> None`, `transaction(conn)` context manager (`BEGIN IMMEDIATE` / commit / rollback), `now_iso() -> str`.
- Produces: `log_event(conn, shop_id: int, actor_user_id: int | None, event_type: str, entity_type: str, entity_id: int | None, details: dict) -> int`, `list_events(conn, shop_id: int, limit: int = 200) -> list[sqlite3.Row]` newest first.
- Tables (columns later tasks rely on):
  - `shops(id, name, district, retail_level)`
  - `users(id, username UNIQUE, password_hash, display_name)`; `memberships(user_id, shop_id, role CHECK IN ('owner','staff','auditor'))`
  - `products(id, shop_id, sku, name_bm, unit, cost_sen, price_sen NULL, target_margin TEXT, controlled_item_code NULL, version INTEGER DEFAULT 1, UNIQUE(shop_id, sku))`
  - `product_aliases(id, shop_id, product_id, alias_norm, unit_norm, pack_size, UNIQUE(shop_id, alias_norm, unit_norm))`
  - `price_limits(id, item_code, item_name, unit, district, retail_level, max_price_sen, valid_from, valid_to, verification CHECK IN ('verified','demo'), source_ref, notes)`
  - `invoices(id, shop_id, uploaded_by, supplier_name, invoice_date, image_path NULL, image_mime NULL, status CHECK IN ('review','manual','proposed'), extraction_source CHECK IN ('runpod','fixture','manual'), extraction_error NULL, created_at)`
  - `invoice_lines(id, invoice_id, position, raw_name, raw_unit, qty TEXT, unit_cost_sen, product_id NULL, pack_size DEFAULT 1, match_status CHECK IN ('matched','uncertain','unknown','confirmed','skipped'), match_score REAL)`
  - `price_proposals(id, shop_id, invoice_id, invoice_line_id, product_id, base_version, old_cost_sen, new_cost_sen, old_price_sen NULL, suggested_price_sen, cap_sen NULL, limit_id NULL, proposed_price_sen NULL, flags TEXT, required_role, status CHECK IN ('pending','blocked','approved','rejected','stale'), explanation TEXT, decided_by NULL, decided_at NULL, final_price_sen NULL, decision_note NULL, created_at)`
  - `audit_events(id, shop_id, actor_user_id, event_type, entity_type, entity_id, details TEXT, created_at)` with `BEFORE UPDATE` and `BEFORE DELETE` triggers `RAISE(ABORT, 'audit_events is append-only')`.

- [ ] **Step 1: Write failing tests:** `init_db` on `:memory:` creates all tables; `log_event` returns id and `list_events` returns details as stored JSON; `UPDATE audit_events ...` and `DELETE FROM audit_events` raise `sqlite3.DatabaseError`; an exception inside `transaction()` rolls back an insert.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `feat: add sqlite schema and append-only audit log`.

### Task 3: Ceilings and pricing rules (pure)

**Files:**
- Create: `src/hargasync/limits.py`, `src/hargasync/pricing.py`, `tests/test_pricing.py`

**Interfaces:**
- Consumes: `price_from_margin`, `MoneyError` (Task 1).
- Produces: `PriceLimit` dataclass (`id, item_code, unit, district, retail_level, max_price_sen, valid_from: date, valid_to: date, verification, source_ref`), `find_applicable_limit(limits, item_code: str, unit: str, district: str, retail_level: str, on: date) -> PriceLimit | None` (exact match on all fields, `valid_from <= on <= valid_to`, lowest `max_price_sen` wins).
- Produces: `ProposalInput` (`old_cost_sen: int, new_cost_sen: int, current_price_sen: int | None, target_margin: Decimal, controlled: bool, limit: PriceLimit | None`), `ProposalResult` (`suggested_price_sen: int, cap_sen: int | None, proposed_price_sen: int | None, flags: list[str], required_role: str, status: str, explanation: list[str]`), `compute_proposal(inp) -> ProposalResult`, `role_can_approve(role: str, required_role: str) -> bool`.
- Flag names (exact): `cost_jump`, `below_cost`, `controlled`, `capped`, `demo_ceiling`, `no_valid_ceiling`, `new_product`, `large_change`.
- Rules: proposed = min(suggested, cap) when a limit applies; controlled with no limit → `status="blocked"`, `proposed_price_sen=None`, flag `no_valid_ceiling`; `below_cost` when proposed < new cost; `required_role="staff"` only if not controlled, no flags and `abs(proposed - current) * 100 <= current * 5`; otherwise `"owner"`. Explanation lines show formula with numbers, cap source (`source_ref`, or `DEMO — fictional ceiling`) and why it routes to owner.

- [ ] **Step 1: Write failing tests** (`find_applicable_limit`): exact match found; wrong district → None; wrong unit → None; date after `valid_to` → None; two matches → lower max returned.
- [ ] **Step 2: Write failing tests** (`compute_proposal`): cost 1000→1150 not `cost_jump`, 1000→1160 is; current 1250, margin 0.20, new cost 1000 → staff (0% change); current 1000 → proposed 1050 is staff (5.00%), proposed 1060 is owner with `large_change`; controlled + verified cap 900 with suggested 1250 → proposed 900, flags include `capped`, `controlled`, `below_cost` when cost 1000, role owner; demo limit → flag `demo_ceiling` and explanation contains `DEMO — fictional ceiling`; controlled no limit → status `blocked`; `current_price_sen=None` → `new_product`, owner; `role_can_approve("staff","owner") is False`, `("owner","staff") is True`, `("auditor","staff") is False`.
- [ ] **Step 3:** Run → FAIL.
- [ ] **Step 4:** Implement.
- [ ] **Step 5:** Run → PASS. Commit `feat: add price-ceiling lookup and pricing rules`.

### Task 4: Catalogue matching

**Files:**
- Create: `src/hargasync/matching.py`, `tests/test_matching.py`

**Interfaces:**
- Produces: `normalize(text: str) -> str` (lowercase, strip accents/punctuation, collapse spaces), `ProductRef(id, sku, name_bm, unit)`, `AliasRef(product_id, alias_norm, unit_norm, pack_size)`, `MatchResult(product_id: int | None, status: str, score: float, pack_size: int)`, `match_line(raw_name: str, raw_unit: str, products: list[ProductRef], aliases: list[AliasRef]) -> MatchResult`.
- Rules in order: alias with same `alias_norm` and `unit_norm` → `matched` with alias pack size, score 1.0; normalized SKU or name equal → `matched` if units equal else `uncertain`; best `difflib.SequenceMatcher` ratio against names and aliases ≥ 0.6 → `uncertain`; else `unknown` with `product_id=None`.

- [ ] **Step 1: Write failing tests:** `normalize("  Gula Pasir, 1KG ") == "gula pasir 1kg"`; alias hit returns pack size 24; exact name + same unit → matched; exact name + different unit → uncertain; typo `"Gula Pasr 1kg"` → uncertain with that product; `"Barang Lain"` → unknown.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `feat: add catalogue matching`.

### Task 5: AI extraction adapter and RunPod handler

**Files:**
- Create: `src/hargasync/extraction.py`, `runpod/requirements.txt`, `runpod/Dockerfile`, `scripts/make_sample_invoice.py`, `fixtures/invoices/sample_invoice.png`, `fixtures/invoices/sample_invoice.json`, `tests/test_extraction.py`, `tests/test_runpod_handler.py`
- Modify: `runpod/handler.py`

**Interfaces:**
- Consumes: `parse_rm` (Task 1), `Settings` (Task 1).
- Produces: `ExtractedLine(name: str, unit: str, qty: Decimal, unit_cost_sen: int)`, `ExtractedInvoice(supplier_name: str, invoice_date: str | None, lines: list[ExtractedLine])`, `ExtractionError(Exception)`, `parse_extraction(payload: dict) -> ExtractedInvoice` (accepts `unit_cost` as number or `"RM x.xx"` string; rejects qty ≤ 0, qty > 10000, cost < 0, > 100 lines, name empty or > 120 chars).
- Produces: extractor classes each with `source: str` and `extract(image: bytes, mime: str) -> ExtractedInvoice`: `RunPodExtractor(api_key, endpoint_id, client: httpx.Client | None = None, timeout_s: float = 120)` (POST `https://api.runpod.ai/v2/{id}/runsync`, body `{"input": {"image_base64", "mime"}}`, poll `/status/{job_id}` while `IN_QUEUE`/`IN_PROGRESS`), `FixtureExtractor(json_path: Path)` (`source="fixture"`), `DisabledExtractor` (raises `ExtractionError("AI reading is not configured")`), `build_extractor(settings) -> extractor`.
- Handler contract: input `{"image_base64": str, "mime": str}` → output `{"invoice": {...}}` or `{"error": str}`. `parse_model_json(text: str) -> dict` strips code fences and takes the outermost `{...}`; model loads lazily on first job from `MODEL_ID` (default `Qwen/Qwen2.5-VL-7B-Instruct`) so tests import the module without torch.

- [ ] **Step 1: Write failing tests:** valid payload parses (`"RM 4.50"` → 450); qty 0, cost -1, 101 lines each raise `ExtractionError`; `RunPodExtractor` with `httpx.MockTransport` returning `COMPLETED` parses; returning `IN_QUEUE` then `COMPLETED` on `/status/` parses (Review Focus 5); `FAILED` or HTTP 500 raises `ExtractionError`; `FixtureExtractor` returns the fixture's lines; `parse_model_json` handles fenced JSON and raises `ValueError` on no JSON.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement adapter and handler (handler guards `runpod.serverless.start` under `if __name__ == "__main__"`). Generate the sample invoice PNG with the script (Pillow), matching its JSON fixture lines to seeded products.
- [ ] **Step 4:** Run → PASS. Commit `feat: add invoice extraction adapter and RunPod handler`.

### Task 6: Auth, sessions, CSRF, app shell, demo seed

**Files:**
- Create: `src/hargasync/auth.py`, `src/hargasync/app.py`, `src/hargasync/seed.py`, `src/hargasync/templates/base.html`, `login.html`, `overview.html`, `src/hargasync/static/style.css`, `tests/support.py`, `tests/test_auth.py`

**Interfaces:**
- Consumes: Tasks 1–2.
- Produces: `hash_password(pw: str) -> str` (PBKDF2-SHA256, 200 000 iterations, random salt), `verify_password(pw: str, stored: str) -> bool`, `CurrentUser(user_id, username, display_name, shop_id, shop_name, district, retail_level, role)`, FastAPI dependencies `get_db(request) -> sqlite3.Connection`, `current_user(request) -> CurrentUser` (redirect 303 to `/login` when absent), `require_roles(user, *roles)` (HTTP 403), `verify_csrf(request, token: str)` (HTTP 403); template global `csrf_token`.
- Produces: `create_app(settings: Settings | None = None, extractor=None) -> FastAPI` — mounts `/static`, `SessionMiddleware(same_site="lax", https_only=settings.https_only)`, routes `GET/POST /login`, `POST /logout`, `GET /`; initialises DB under `settings.data_dir` and seeds when empty and `demo_seed`.
- Produces: `seed_demo(conn, password: str) -> None`: shop A "Kedai Runcit Pak Ali" (district `Petaling`, retail `runcit`) with users `owner_ali` (owner), `staff_mei` (staff), `auditor_raj` (auditor); shop B "Mini Market Seri Kembangan" with `owner_siti`; ~8 BM products in shop A matching the sample invoice, one controlled (`ayam_standard`), plus one alias with pack size; price limits: one `demo` for `ayam_standard`/`kg`/`Petaling`/`runcit` valid around today, one expired, one for another district.
- `tests/support.py`: `make_client(extractor=None) -> (TestClient, Settings)` on a temp data dir; `login(client, username)`; `csrf(client) -> str`.

- [ ] **Step 1: Write failing tests:** `GET /` without session → 303 `/login`; wrong password → 401 and page shows error; `owner_ali` login → 303 `/`, overview shows shop name; `POST /logout` without CSRF → 403; `verify_password` round-trips and rejects wrong password.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `feat: add auth, sessions, CSRF and demo seed`.

### Task 7: Invoice intake and review

**Files:**
- Create: `src/hargasync/invoices.py`, `src/hargasync/routes_invoices.py`, `src/hargasync/templates/review.html`, `tests/test_invoices.py`
- Modify: `src/hargasync/app.py` (include router), `overview.html` (upload form + "enter manually")

**Interfaces:**
- Consumes: Tasks 1–6 (`match_line`, `compute_proposal`, `find_applicable_limit`, `log_event`, `transaction`).
- Produces: `UploadError(ValueError)`, `validate_image(data: bytes) -> str` (JPEG/PNG/WebP via Pillow `verify()`, ≤ 8 MB, returns mime), `create_invoice(conn, user, image: bytes | None, extractor, data_dir: Path) -> int` (stores file at `data_dir/uploads/<shop_id>/<uuid>.<ext>`; extraction failure → status `manual` with `extraction_error`), `LineEdit(position, raw_name, raw_unit, qty: Decimal, unit_cost_sen: int, product_id: int | None, pack_size: int, skip: bool)`, `save_lines(conn, user, invoice_id, lines: list[LineEdit]) -> None` (re-matches, user-chosen product → `confirmed`), `confirm_invoice(conn, user, invoice_id: int, on: date) -> list[int]` (refuses unresolved `uncertain`/`unknown` lines and duplicate products; new cost per product unit = `unit_cost_sen / pack_size` rounded half-up to the sen; one transaction creates proposals, saves aliases for confirmed lines, sets invoice `proposed`, logs `invoice_confirmed`).
- Routes: `POST /invoices` (upload; empty file field → manual invoice), `GET /invoices/{id}`, `GET /invoices/{id}/image`, `POST /invoices/{id}/lines`, `POST /invoices/{id}/confirm`. Auditor gets 403 on all POSTs. Unknown or other-shop id → 404.

- [ ] **Step 1: Write failing tests:** upload sample PNG with `FixtureExtractor` → redirect to review, lines saved, matched lines carry product ids, page shows `Simulated AI`; upload `b"not an image"` → 400, no invoice row, no file in uploads (Review Focus 1); 9 MB payload → 400; `DisabledExtractor` → invoice status `manual`, zero lines, page offers manual entry; `owner_siti` GET shop A invoice and its image → 404; auditor POST upload → 403; confirm with an `unknown` line → error, no proposals; two lines mapped to the same product → confirm refuses with `duplicate product` (Review Focus 3); valid confirm → proposals created and alias saved for a confirmed pack-size mapping; a carton line at `RM 36.00` with pack size 24 → proposal `new_cost_sen == 150`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `feat: add invoice upload, AI extraction and review`.

### Task 8: Proposals and atomic approval

**Files:**
- Create: `src/hargasync/approvals.py`, `src/hargasync/routes_proposals.py`, `src/hargasync/templates/proposals.html`, `tests/test_approvals.py`
- Modify: `src/hargasync/app.py`

**Interfaces:**
- Consumes: Tasks 2–3, 6–7.
- Produces: `ApprovalError(Exception)` with `.code` in `{"not_found","already_decided","stale","forbidden","blocked","over_cap","needs_reason","bad_price"}`, `approve_proposal(conn, user, proposal_id: int, override_price_sen: int | None, note: str, on: date) -> int` (returns final price), `reject_proposal(conn, user, proposal_id: int, note: str) -> None`.
- Algorithm inside one `transaction`: load proposal for `user.shop_id` (else `not_found`); status must be `pending` (`blocked` → `blocked`, other → `already_decided`); product `version` must equal `base_version` (else mark `stale`, log, raise `stale`); recompute `compute_proposal` with current product and limits for `on`; `role_can_approve` on the recomputed role (else `forbidden`); override only by owner, requires non-empty note, must be > 0 and ≤ cap; `UPDATE products ... WHERE id=? AND version=?` and `UPDATE price_proposals ... WHERE id=? AND status='pending'` must each affect 1 row; log `price_approved` with old/new price, cap, source, approver.
- Routes: `GET /proposals` (pending first, then recent decisions; shows old/new cost, suggested, cap + source or `DEMO — fictional ceiling`, flags, required role, explanation), `POST /proposals/{id}/approve` (fields `override_price`, `note`), `POST /proposals/{id}/reject`.

- [ ] **Step 1: Write failing tests:** staff approves a staff-eligible proposal → product price updated, version +1, one `price_approved` event; staff on owner-required → 403 / `forbidden`, no change; staff override → `forbidden`; owner override above cap → `over_cap`; override without note → `needs_reason`; approve twice → second `already_decided`, version incremented once, one event; two proposals for one product from two invoices → approving second after first → `stale`; blocked proposal → `blocked`; `owner_siti` approving shop A proposal → 404; proposals page shows `DEMO — fictional ceiling` for the demo-capped item.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `feat: add proposal inbox and atomic approval`.

### Task 9: Tags, activity, catalogue

**Files:**
- Create: `src/hargasync/routes_outputs.py`, `src/hargasync/templates/tags.html`, `activity.html`, `catalogue.html`, `tests/test_outputs.py`
- Modify: `src/hargasync/app.py`, `base.html` (nav)

**Interfaces:**
- Consumes: Tasks 2, 6, 8.
- Routes: `GET /tags` (checkbox list of products, products approved in the last 7 days pre-ticked), `GET /tags/print?ids=1&ids=2` (A4 sheet, 3 × 8 labels, `@page { size: A4 }`; each label: `name_bm`, unit, `format_rm(price_sen)`, SKU, `Harga berkuat kuasa: dd/mm/yyyy`; controlled items add `Barang kawalan harga` and, for demo caps, `DEMO — fictional ceiling`; products without a price are skipped and listed), `GET /activity` (audit timeline), `GET /catalogue`, `POST /catalogue` (owner only: add product).

- [ ] **Step 1: Write failing tests:** after an approval, `/tags/print?ids=<id>` contains the approved `format_rm` price and `Harga berkuat kuasa`; ids from shop B are ignored; auditor can GET `/activity` and sees `price_approved`; staff `POST /catalogue` → 403; owner adds product and it appears in `/catalogue`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `feat: add printable BM tags, activity and catalogue`.

### Task 10: Evidence benchmark and README

**Files:**
- Create: `scripts/benchmark.py`, `fixtures/breaches.json`, `tests/test_benchmark.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: `compute_proposal`, `find_applicable_limit`, `parse_extraction`.
- Produces: `run_breach_benchmark(path: Path) -> dict` (`{"cases": n, "intercepted": k, "rate": k/n}`; a case is intercepted when its expected flag or status is produced), CLI prints results with date and fixture name. `fixtures/breaches.json`: ≥ 10 planted violations (above-cap, expired cap, wrong district, cost jump, below cost, large change).
- README: fill every template section for HargaSync (problem, solution, features, stack, architecture, run on Replit/locally, demo accounts, how Replit and RunPod are used, RunPod deploy steps, evidence results, limitations, AI-tool disclosure), keep the Drive link and checklist.

- [ ] **Step 1: Write failing test:** `run_breach_benchmark(fixtures/breaches.json)["rate"] == 1.0`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement and write README. **Step 4:** Full suite `python -m unittest discover -s tests -t .` → all PASS.
- [ ] **Step 5:** Commit `docs: fill README and add breach benchmark`.
