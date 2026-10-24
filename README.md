> [!IMPORTANT]
> ## 📁 Submission Documents & Templates
> **All required submission templates are in the Google Drive folder below. Download them before you start.**
>
> ### 👉 [**OPEN THE GOOGLE DRIVE FOLDER**](https://drive.google.com/drive/folders/1xw7c2aN8N-at8hPEULzkcU76e_FFb0Ef) 👈

---

# SURPrice

> From supplier cost to the right shelf price: an AI-assisted pricing and price-tag workflow for Malaysian micro-retailers (kedai runcit and mini-markets).

---

## Team Information

| Field                  | Details                                     |
| ---------------------- | ------------------------------------------- |
| **Team Name**          | SURPrice                                    |
| **Team Domain**        | Domain 2 — Orbyte Smart SME Challenge: Less Busywork, Better Business (Alpha Red Solutions) |
| **SDG Track (1–17)**   | SDG 8 — Decent Work and Economic Growth (targets 8.2 and 8.3) |
| **Team Leader**        | Ahmad Zhafir bin Razali                     |
| **University**         | Universiti Putra Malaysia (UPM)             |
| **Number of Members**  | 3                                           |

## Links

| Resource          | Link                                           |
| ----------------- | ---------------------------------------------- |
| GitHub Repository | https://github.com/WanHafizuddin/SURPrice      |
| Replit Project    | https://replit.com/@whafiz012/SURPrice         |
| Live Demo         | https://surprice.replit.app (demo logins are shown on the login page) |
| RunPod Endpoint   | https://api.runpod.ai/v2/opdzmifqcyfxio       |
| Slide Deck        | https://example.com/slides                     |
| Demo Video        | https://example.com/demo-video                 |

---

## Overview

### Problem

When a supplier changes a cost, a small shop has to read a messy invoice, find each item in its own list, work out a new selling price that keeps its margin, check whether the item is under a festive price-control ceiling, and replace the shelf label. Done by hand, shelf labels lag behind costs, margins leak, and a controlled item can end up priced above its legal maximum.

### Solution

SURPrice turns one supplier invoice photo into reviewable price proposals, an authorised catalogue update and a print-ready Bahasa Malaysia shelf-tag sheet.

1. **Capture**: staff photograph the invoice (or type the lines if reading fails).
2. **Understand**: a vision-language model on RunPod transcribes supplier, items, units, quantities and unit costs into JSON. SURPrice validates that JSON and matches each line to the shop's catalogue, flagging uncertain names and unit mismatches (for example a *karton* of 24 tins).
3. **Propose**: deterministic rules compute the selling price, `cost ÷ (1 − target margin)` rounded **up** to RM0.10, cap controlled items at the ceiling for the exact item, unit, district, retail level and date, and flag cost jumps over 15% and below-cost results.
4. **Approve**: staff may approve small non-controlled changes (5% or less, no warnings); everything else goes to the owner. Approval re-checks the rules, the user's role and the catalogue version, then updates the price and writes the audit record in one database transaction.
5. **Publish**: print A4 sheets of BM shelf tags straight from the approved catalogue, and review the append-only activity log.

The AI only reads documents. It never decides a legal ceiling, approves a price or edits the catalogue.

### Key Features

- **Invoice photo to structured lines**: RunPod-hosted Qwen2.5-VL reads mixed BM/English invoices; strict validation; manual entry fallback whenever reading fails.
- **Catalogue matching with unit checks**: exact, alias and fuzzy matching; confirmed pack sizes are remembered for the next invoice.
- **Explainable price proposals**: every proposal shows the formula with real numbers, the ceiling and its source, warnings and who must approve.
- **Price-control safeguards**: a controlled item with no valid ceiling for that district, unit and date is blocked; demo ceilings are always labelled `DEMO — fictional ceiling`.
- **Server-enforced roles and shop isolation**: owner, staff and read-only auditor; one shop can never see or change another's data.
- **Atomic, auditable approvals**: repeated or stale approvals write nothing; the activity log cannot be edited or deleted.
- **Printable BM shelf tags**: 24 tags per A4 sheet showing *Harga berkuat kuasa* and a *Barang kawalan harga* marker for controlled items.

### Tech Stack

| Layer         | Technology                                                        |
| ------------- | ----------------------------------------------------------------- |
| Frontend      | Server-rendered HTML (Jinja2), CSS, no build step                 |
| Backend       | Python 3.11+, FastAPI, Uvicorn                                    |
| Database      | SQLite (standard library), append-only audit triggers             |
| AI / Compute  | RunPod Serverless GPU running Qwen2.5-VL-7B-Instruct (Transformers) |
| Hosting / Dev | Replit                                                            |

### The Domain 2 Journey

| Step | In SURPrice |
| ---- | ------------ |
| **Trigger** | A supplier invoice arrives and staff upload its photo. |
| **Connected data** | The invoice lines are joined with the shop's catalogue (cost, current price, target margin, pack sizes) and the price ceiling for the shop's district, retail level and date. |
| **Decision logic** | AI only reads the photo. Plain rules work out the price, apply the ceiling, raise warnings and decide who must approve. |
| **Human approval** | Staff approve small, warning-free changes; the owner approves everything else. Approval re-checks role, rules and catalogue version. |
| **Visible outcome** | The catalogue price changes, a BM shelf-tag sheet is ready to print, and the change is written to the activity log. |

### Orbyte Fit and Reuse

SURPrice is designed as a **pricing module inside the Orbyte hub**, not a standalone app. It adds a capability Orbyte does not have today, supplier-cost-to-shelf-price pricing with price-control checks, and does not repeat Orbyte's HR or administrative functions.

- **Shares the hub's foundations.** Users, roles and shops would come from Orbyte. In this MVP they are simulated locally (owner, staff and read-only auditor, with one shop never seeing another's data).
- **Data in (our interface assumptions, not live Orbyte APIs):** supplier invoices from the hub's procurement inbox or WhatsApp intake, the shop's product catalogue, and the shop's district and retail level.
- **Data out:** approved prices back to the hub catalogue and any connected POS or online store, a printable shelf-tag sheet, and approval events into the hub's activity feed.
- **Built for many SMEs.** Everything is set per shop: district, retail level, per-product target margin, product aliases and pack sizes. The demo already runs two separate shops on one deployment. The same flow suits any small business that buys by the carton and sells by the piece; kedai runcit and mini-markets are the first target.
- **Reusable building blocks.** The core logic is plain Python with no web code, so other Orbyte modules could reuse it:
  - `money.py`: sen arithmetic and RM0.10 rounding
  - `pricing.py`: margin, ceiling, warning and approval-routing rules
  - `limits.py`: which price ceiling applies for an item, unit, district, retail level and date
  - `matching.py`: invoice line to catalogue product, with unit and pack-size checks
  - `extraction.py`: invoice-reader adapter (RunPod, Simulated AI or manual) with strict JSON validation

### Business Benefit

**Measured now**

- 13 of 13 planted rule breaches intercepted (above ceiling, expired, wrong-district or wrong-unit ceiling, cost jump, below cost, large change, new product). See [Evidence](#evidence).

**Expected (team targets, not yet measured with real shops)**

- **Time saved:** under 3 minutes from a 15-line invoice to printable tags. The owner no longer reads each line, looks up each item, works out each price and rewrites each label by hand.
- **Errors avoided:** every price comes from the same rule and rounding, so labels match approved prices (target 98%+); a controlled item with no valid ceiling is blocked instead of guessed.
- **Less training needed:** each proposal explains itself in plain words, with the formula, the real numbers, the ceiling and who must approve, so new staff can follow it without formal training.
- **How we will check:** time the same invoice done by hand and in SURPrice with shop owners, and compare printed tags against approved prices.

**SDG contribution**

- **SDG 8.2:** higher productivity for micro-retailers through simple technology upgrades.
- **SDG 8.3:** supports micro and small enterprises by protecting their margins and keeping them within price-control rules.

---

## Project Structure

```
.
├── docs/superpowers/           # Design spec and implementation plan
├── fixtures/
│   ├── breaches.json           # Planted rule violations for the benchmark
│   └── invoices/               # Fictional sample invoice photo + expected AI output
├── runpod/
│   ├── handler.py              # RunPod serverless worker: invoice photo -> JSON
│   └── Dockerfile              # Worker image and its Python dependencies
├── scripts/
│   ├── benchmark.py            # Prints measured evidence
│   └── make_sample_invoice.py  # Regenerates the sample invoice photo
├── src/
│   ├── main.py                 # Entry point (Replit Run button)
│   └── hargasync/
│       ├── app.py              # FastAPI app, sessions, login
│       ├── money.py            # Sen arithmetic and RM0.10 rounding
│       ├── pricing.py          # Margin, ceiling, warning and routing rules
│       ├── limits.py           # Which price ceiling applies
│       ├── matching.py         # Invoice line -> catalogue product
│       ├── extraction.py       # AI adapter (RunPod / Simulated AI / off) + validation
│       ├── invoices.py         # Upload, review, create proposals
│       ├── approvals.py        # Atomic approve / reject
│       ├── audit.py, db.py, schema.sql, seed.py, auth.py, web.py
│       ├── routes_*.py         # Pages
│       ├── templates/          # HTML
│       └── static/style.css
├── submission/                 # Required submission documents
├── tests/                      # unittest suite
├── .env.example
├── .replit
├── requirements.txt
└── README.md
```

### Architecture

```
Phone / browser ──► Replit: FastAPI app ──► SQLite (catalogue, invoices, proposals, audit log)
                         │                    └─ private invoice photos (data/uploads, never public)
                         │
                         ├─► RunPod Serverless endpoint (GPU) ── Qwen2.5-VL reads the photo, returns JSON
                         │        ▲ only the photo is sent; pricing never leaves the app
                         │
                         └─► Deterministic rules ──► approval (role + version re-check, one transaction)
                                                       └─► BM shelf-tag sheet (A4, print from browser)
```

---

## How to Run

### Option 1 — Run on Replit (Recommended)

1. Import this repository via **Create Repl → Import from GitHub**.
2. Open the **Secrets** tab (🔒) and add the variables from `.env.example`:
   - `HARGASYNC_SECRET_KEY` (any long random string)
   - `RUNPOD_API_KEY` and `RUNPOD_ENDPOINT_ID` (leave unset to use the labelled Simulated AI)
   - `HTTPS_ONLY=1` for a deployment
3. Click **Run**. Replit uses `.replit` to start `python src/main.py` on port 8000. If it reports a missing package, run `pip install -r requirements.txt` in the **Shell** tab and click **Run** again.
4. Log in with a demo account (below).
5. To publish: **Deploy → Reserved VM**. The deployment installs `requirements.txt` (the `build` step in `.replit`), then starts the same command. Add the same Secrets to the deployment, with `HTTPS_ONLY=1`.

### Option 2 — Run Locally

```bash
git clone https://github.com/WanHafizuddin/SURPrice.git
cd SURPrice
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python src/main.py               # http://localhost:8000
```

### Option 3 — Deploy on Render

`render.yaml` is a Render Blueprint for a Python web service.

1. In the [Render dashboard](https://dashboard.render.com), choose **New → Blueprint** and connect this GitHub repository (Render asks for access to private repos).
2. When asked for `RUNPOD_API_KEY` and `RUNPOD_ENDPOINT_ID`, fill both to read invoices on RunPod, or leave both empty to use the labelled Simulated AI.
3. Click **Apply**. Render installs `requirements.txt`, runs `python src/main.py` on its `PORT`, generates `HARGASYNC_SECRET_KEY` and serves the app over HTTPS at `https://hargasync-<id>.onrender.com`.

On the **free** plan the service sleeps after about 15 minutes idle (the first visit then takes up to a minute) and its disk is wiped on every restart or deploy: demo data re-seeds, uploaded invoices and approvals are lost. To keep data, use a paid plan with a disk by changing the service in `render.yaml`:

```yaml
    plan: starter
    disk:
      name: hargasync-data
      mountPath: /var/data
      sizeGB: 1
```

and adding the environment variable `HARGASYNC_DATA_DIR=/var/data`. Render also hosts the app only: the competition still requires Replit and RunPod use (see below).

### Demo accounts

The first start seeds fictional data. Every demo account uses the password in `DEMO_PASSWORD` (default `demo1234`).

| Username      | Role    | Shop                                  |
| ------------- | ------- | ------------------------------------- |
| `owner_ali`   | Owner   | Kedai Runcit Pak Ali (DEMO), Petaling |
| `staff_mei`   | Staff   | Kedai Runcit Pak Ali (DEMO)           |
| `auditor_raj` | Auditor | Kedai Runcit Pak Ali (DEMO)           |
| `owner_siti`  | Owner   | Mini Market Seri Kembangan (DEMO)     |

Suggested demo: log in as `staff_mei`, upload [`fixtures/invoices/sample_invoice.png`](fixtures/invoices/sample_invoice.png) (also downloadable inside the app), resolve the three flagged lines, create proposals, approve the small changes, then log in as `owner_ali` to approve the capped chicken price and the 16% cooking-oil jump, and print tags.

### Run Tests

```bash
python -m unittest discover -s tests -t .
```

### Measure the evidence

```bash
python scripts/benchmark.py
```

---

## How We Use Replit *(Required)*

- **Development:** the team codes in a shared Repl imported from this repository.
- **Hosting:** the FastAPI app is deployed with Replit Deployments at the Live Demo link above. `.replit` installs `requirements.txt` as the deployment's build step, then runs `python src/main.py`.
- **Secrets:** `HARGASYNC_SECRET_KEY` and the RunPod credentials live in Replit Secrets, never in the code.
- **Deployment type:** `.replit` targets a Reserved VM (`gce`): one always-on instance, so SQLite and uploaded photos stay put between requests. Autoscale would scale to zero and lose them. A redeploy still resets the disk; the demo data re-seeds automatically.
- **Secrets for a deployment:** set `HARGASYNC_SECRET_KEY` (at least 16 characters; placeholders are refused) and `HTTPS_ONLY=1`.

📄 Proof of use: [`submission/SDC2026_SURPrice_Replit_POU.pdf`](submission/SDC2026_SURPrice_Replit_POU.pdf)

## How We Use RunPod *(Required)*

- **Workload:** invoice reading. A vision-language model (`Qwen/Qwen2.5-VL-7B-Instruct`, configurable with `MODEL_ID`) transcribes each invoice photo into JSON on a RunPod GPU.
- **Setup:** `runpod/handler.py` runs as a queue-based **RunPod Serverless Endpoint** that RunPod builds straight from this GitHub repository:
  1. In RunPod, choose **Serverless → New Endpoint → GitHub Repo**, pick this repository and branch `main`, and set the Dockerfile path to `runpod/Dockerfile` with `runpod` as the build context.
  2. Pick a 24 GB GPU from the previous generation (the image uses CUDA 12.4, while RunPod's latest-generation GPUs need CUDA 12.8+), with 0 active workers and 1 max worker so the endpoint costs nothing while idle.
  3. Optionally cache `Qwen/Qwen2.5-VL-7B-Instruct` with RunPod's cached-model setting and set `HF_HOME=/runpod-volume/huggingface-cache`, so cold starts skip the model download.
  4. Put the endpoint ID and an API key into Replit Secrets.

  Without GitHub, build the image yourself with `docker build -t <dockerhub-user>/hargasync-reader:latest runpod`, push it, and create the endpoint from that image.
- **Integration:** the app sends the photo to `/runsync` with `RUNPOD_API_KEY` and `RUNPOD_ENDPOINT_ID`, polls `/status/{id}` during cold starts, validates the returned JSON and falls back to manual entry on any failure.

Example request:

```bash
curl -X POST https://api.runpod.ai/v2/$RUNPOD_ENDPOINT_ID/runsync \
  -H "Authorization: Bearer $RUNPOD_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"input": {"image_base64": "<base64 photo>", "mime": "image/png"}}'
```

📄 Proof of use: [`submission/SDC2026_SURPrice_Runpod_POU.pdf`](submission/SDC2026_SURPrice_Runpod_POU.pdf)

---

## Evidence

Measured with `python scripts/benchmark.py` in the Replit Shell on 24 October 2026, with invoice reading on the live RunPod endpoint:

| Measure | Fixture | Result |
| ------- | ------- | ------ |
| Planted rule breaches intercepted (above ceiling, expired/wrong-district/wrong-unit ceiling, cost jump, below cost, large change, new product) | `fixtures/breaches.json`, 13 synthetic cases | 13/13 (100%) |
| Invoice lines read exactly (name, quantity, unit cost) | `fixtures/invoices/`, 1 invoice, 8 lines | 8/8 (100%) on RunPod. This is one clean, computer-generated invoice, so it shows the pipeline works end to end, not accuracy on real phone photos. |
| Automated tests | `tests/` | `python -m unittest discover -s tests -t .` |

Targets from the proposal: 98%+ tag accuracy against approved prices, under 3 minutes from a 15-line invoice to printable tags, 100% of planted breaches intercepted. All ceilings, invoices, shops and people in the demo are fictional.

## Privacy and PDPA

**In this MVP** every shop, user, product, invoice and price ceiling is synthetic and created by the team. No real personal, customer or company records are used.

**Personal data a real deployment would hold:** shop users' usernames, display names and password hashes, and invoice photos, which may show a supplier's contact name or phone number. SURPrice collects no data about the shop's end customers.

How a real deployment would follow the seven principles of Malaysia's Personal Data Protection Act 2010 (PDPA):

| PDPA principle | Already in the MVP | Needed for a real deployment |
| -------------- | ------------------ | ---------------------------- |
| **General** (lawful purpose, only what is needed) | Only account details and invoice photos are collected, and only for pricing. | Record the purpose in the shop's agreement with Orbyte. |
| **Notice and Choice** | — | A plain BM/English notice before first use saying what is collected and why. |
| **Disclosure** | Invoice photos go only to the team's own RunPod endpoint for reading; prices and the catalogue never leave the app. | List RunPod as a data processor; no sharing for any other purpose. |
| **Security** | Roles checked on the server, shop isolation, photos served only to signed-in users of that shop with `no-store` caching, PBKDF2-SHA256 password hashes, CSRF protection, Secure cookies over HTTPS, keys kept in Replit Secrets. | Encrypted backups, access reviews, a breach response plan. |
| **Retention** | — | Delete invoice photos after a set period once their proposals are decided; keep only the activity log needed for audit. |
| **Data Integrity** | AI output is validated, every line is reviewed by a person, and the activity log is append-only. | Let users correct their own profile details. |
| **Access** | Every signed-in user can see their own shop's activity log. | A simple request flow for users to see or correct their personal data. |

The PDPA (Amendment) Act 2024 also requires data breach notification and a data protection officer; a production version would plan for both and assess the cross-border transfer when invoice photos are read on a GPU outside Malaysia.

## Challenges & Learnings

- Keeping AI out of decisions: the model only transcribes; every price comes from rules a person can read.
- Price-control data is location-, unit- and date-specific, so a missing or expired ceiling must block a change rather than fall back to a guess.
- Atomic approval (version check, price update and audit write in one transaction) is what makes double-clicks and two invoices for the same product safe.

## Future Improvements

- [ ] Measure reading accuracy on real, consented supplier invoices through the RunPod endpoint.
- [ ] Load verified, dated ceilings for one locality from official gazette notices.
- [ ] Shelf-photo check comparing the printed tag against the approved price.
- [ ] Orbyte / POS catalogue sync and WhatsApp invoice intake (currently out of scope).

## Team

| Name                                  | Role | GitHub                                           |
| ------------------------------------- | ---- | ------------------------------------------------ |
| Ahmad Zhafir bin Razali               | Team Leader | [@username](https://github.com/username)         |
| Nor Syameel Azraie bin Nor Ezlie Azram | Role | [@username](https://github.com/username)         |
| Wan Hafizuddin bin Wan Harun          | Role | [@WanHafizuddin](https://github.com/WanHafizuddin) |

---

## Submission Checklist

- [x] Team name, domain (Domain 1 / Domain 2) and SDG track filled in
- [ ] Slide deck link added
- [ ] Demo video link added
- [ ] Replit used, with proof of use in `submission/`
- [ ] RunPod used, with proof of use in `submission/`
- [ ] Preliminary submission completed (`SDC2026_SURPrice_Preliminary.pdf`)
- [ ] Technology declaration completed (`SDC2026_SURPrice_TechDeclaration.pdf`)
- [x] Submission files renamed with your team name (replace `TeamName`)
- [x] "How to Run" steps verified
- [x] No API keys or secrets committed to the repository

### Declarations to include

- **AI-assisted development:** this codebase was written with Claude Code (Anthropic), reviewed and tested by the team. Declare it in the Technology Declaration, section 4.3.
- **Third-party:** FastAPI, Starlette, Uvicorn, Jinja2, python-multipart, itsdangerous, httpx, Pillow (app); runpod, PyTorch, Transformers, Accelerate and the Qwen2.5-VL-7B-Instruct model weights (worker). Check each license when filling the declaration.
- **Data sent to third parties:** invoice photos are sent to the team's RunPod endpoint for reading. No customer personal data is collected.

## License

This project is licensed under the [Apache License 2.0](LICENSE).
