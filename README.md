> [!IMPORTANT]
> ## 📁 Submission Documents & Templates
> **All required submission templates are in the Google Drive folder below. Download them before you start.**
>
> ### 👉 [**OPEN THE GOOGLE DRIVE FOLDER**](https://drive.google.com/drive/folders/1xw7c2aN8N-at8hPEULzkcU76e_FFb0Ef) 👈

---

# HargaSync

> From supplier cost to the right shelf price: an AI-assisted pricing and price-tag workflow for Malaysian micro-retailers (kedai runcit and mini-markets).

---

## Team Information

| Field                  | Details                                     |
| ---------------------- | ------------------------------------------- |
| **Team Name**          | Your Team Name                              |
| **Team Domain**        | Domain 1 / Domain 2 *(choose one)*          |
| **SDG Track (1–17)**   | SDG 8 — Decent Work and Economic Growth     |
| **Team Leader**        | Leader Name                                 |
| **University**         | University Name(s)                          |
| **Number of Members**  | e.g. 4                                      |

## Links

| Resource          | Link                                           |
| ----------------- | ---------------------------------------------- |
| GitHub Repository | https://github.com/WanHafizuddin/HargaSync     |
| Replit Project    | https://replit.com/@your-username/your-project |
| Live Demo         | https://your-project.replit.app                |
| RunPod Endpoint   | https://api.runpod.ai/v2/your-endpoint-id      |
| Slide Deck        | https://example.com/slides                     |
| Demo Video        | https://example.com/demo-video                 |

---

## Overview

### Problem

When a supplier changes a cost, a small shop has to read a messy invoice, find each item in its own list, work out a new selling price that keeps its margin, check whether the item is under a festive price-control ceiling, and replace the shelf label. Done by hand, shelf labels lag behind costs, margins leak, and a controlled item can end up priced above its legal maximum.

### Solution

HargaSync turns one supplier invoice photo into reviewable price proposals, an authorised catalogue update and a print-ready Bahasa Malaysia shelf-tag sheet.

1. **Capture**: staff photograph the invoice (or type the lines if reading fails).
2. **Understand**: a vision-language model on RunPod transcribes supplier, items, units, quantities and unit costs into JSON. HargaSync validates that JSON and matches each line to the shop's catalogue, flagging uncertain names and unit mismatches (for example a *karton* of 24 tins).
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
│   ├── Dockerfile              # Worker image
│   └── requirements.txt
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
3. Click **Run**. Replit uses `.replit` to start `python src/main.py` on port 8000.
4. Log in with a demo account (below).

### Option 2 — Run Locally

```bash
git clone https://github.com/WanHafizuddin/HargaSync.git
cd HargaSync
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python src/main.py               # http://localhost:8000
```

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
- **Hosting:** the FastAPI app is deployed with Replit Deployments at the Live Demo link above (`.replit` → `python src/main.py`).
- **Secrets:** `HARGASYNC_SECRET_KEY` and the RunPod credentials live in Replit Secrets, never in the code.
- **Deployment type:** `.replit` targets a Reserved VM (`gce`): one always-on instance, so SQLite and uploaded photos stay put between requests. Autoscale would scale to zero and lose them. A redeploy still resets the disk; the demo data re-seeds automatically.
- **Secrets for a deployment:** set `HARGASYNC_SECRET_KEY` (at least 16 characters; placeholders are refused) and `HTTPS_ONLY=1`.

📄 Proof of use: [`submission/SDC2026_TeamName_Replit_POU.pdf`](submission/SDC2026_TeamName_Replit_POU.pdf)

## How We Use RunPod *(Required)*

- **Workload:** invoice reading. A vision-language model (`Qwen/Qwen2.5-VL-7B-Instruct`, configurable with `MODEL_ID`) transcribes each invoice photo into JSON on a RunPod GPU.
- **Setup:** `runpod/handler.py` is deployed as a **RunPod Serverless Endpoint**:
  1. Build and push the worker image: `docker build -t <dockerhub-user>/hargasync-reader:latest runpod`, then `docker push` it.
  2. In RunPod, create a Serverless endpoint from that image (a 24 GB GPU is enough), and optionally attach a network volume so model weights are cached at `/runpod-volume/hf-cache`.
  3. Put the endpoint ID and an API key into Replit Secrets.
- **Integration:** the app sends the photo to `/runsync` with `RUNPOD_API_KEY` and `RUNPOD_ENDPOINT_ID`, polls `/status/{id}` during cold starts, validates the returned JSON and falls back to manual entry on any failure.

Example request:

```bash
curl -X POST https://api.runpod.ai/v2/$RUNPOD_ENDPOINT_ID/runsync \
  -H "Authorization: Bearer $RUNPOD_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"input": {"image_base64": "<base64 photo>", "mime": "image/png"}}'
```

📄 Proof of use: [`submission/SDC2026_TeamName_Runpod_POU.pdf`](submission/SDC2026_TeamName_Runpod_POU.pdf)

---

## Evidence

Measured with `python scripts/benchmark.py` on 23 October 2026:

| Measure | Fixture | Result |
| ------- | ------- | ------ |
| Planted rule breaches intercepted (above ceiling, expired/wrong-district/wrong-unit ceiling, cost jump, below cost, large change, new product) | `fixtures/breaches.json`, 13 synthetic cases | 13/13 (100%) |
| Invoice lines read exactly (name, quantity, unit cost) | `fixtures/invoices/`, 1 invoice, 8 lines | Not yet measured on RunPod. Simulated AI scores 100% by construction, which is not evidence. |
| Automated tests | `tests/` | `python -m unittest discover -s tests -t .` |

Targets from the proposal: 98%+ tag accuracy against approved prices, under 3 minutes from a 15-line invoice to printable tags, 100% of planted breaches intercepted. All ceilings, invoices, shops and people in the demo are fictional.

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

| Name        | Role                | GitHub                                   |
| ----------- | ------------------- | ---------------------------------------- |
| Member Name | Team Lead / Backend | [@username](https://github.com/username) |
| Member Name | Frontend            | [@username](https://github.com/username) |
| Member Name | AI / RunPod         | [@username](https://github.com/username) |

---

## Submission Checklist

- [ ] Team name, domain (Domain 1 / Domain 2) and SDG track filled in
- [ ] Slide deck link added
- [ ] Demo video link added
- [ ] Replit used, with proof of use in `submission/`
- [ ] RunPod used, with proof of use in `submission/`
- [ ] Preliminary submission completed (`SDC2026_TeamName_Preliminary.pdf`)
- [ ] Technology declaration completed (`SDC2026_TeamName_TechDeclaration.pdf`)
- [ ] Submission files renamed with your team name (replace `TeamName`)
- [ ] "How to Run" steps verified
- [ ] No API keys or secrets committed to the repository

### Declarations to include

- **AI-assisted development:** this codebase was written with Claude Code (Anthropic), reviewed and tested by the team. Declare it in the Technology Declaration, section 4.3.
- **Third-party:** FastAPI, Starlette, Uvicorn, Jinja2, python-multipart, itsdangerous, httpx, Pillow (app); runpod, PyTorch, Transformers, Accelerate and the Qwen2.5-VL-7B-Instruct model weights (worker). Check each license when filling the declaration.
- **Data sent to third parties:** invoice photos are sent to the team's RunPod endpoint for reading. No customer personal data is collected.

## License

This project is licensed under the [Apache License 2.0](LICENSE).
