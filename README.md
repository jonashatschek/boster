# Boster

A personal web app for evaluating apartments for sale in Sweden (*bostadsrätter*) and the housing cooperatives (*bostadsrättsföreningar*) that own the buildings.

Upload a cooperative's annual report (*årsredovisning*) as a PDF, or paste a link to one. Boster reads the key figures and financial statements, calculates its own KPIs, rates the main financial risks with documented rules, and shows where every number came from, down to the page in the PDF.

The user interface is in Swedish. Code and documentation are in English.

The full product specification is in [specs/spec.md](specs/spec.md).

## Status

| Step | Content | Status |
|---|---|---|
| 1 | Domain model, KPI formulas, risk rules, PDF extraction, tests | Done |
| 2 | Upload a report by file or link → cooperative page with KPIs, charts, sources and manual corrections | Done |
| 2b | Compare 2–4 cooperatives side by side | Done |
| 3 | Import a listing (URL, pasted text, or manual entry) → property page linked to a cooperative | Next |
| 4 | Swedish AI summaries with links to the evidence | Planned |
| 5 | Comparing properties side by side, and saved comparisons | Planned |

## What it does today

- **Add documents** by drag and drop, file picker, or link. Uploading the same file twice reuses the stored copy.
- **Identifies the cooperative** by its organisation number. Cooperatives with similar names are never merged. If a document ends up under the wrong cooperative, you can move it.
- **Reads figures from the report:**
  - The multi-year overview (*flerårsöversikt*), including the key figures required since 2023: debt per m², savings per m², interest sensitivity, energy cost per m², fee per m², and the fee share of revenue.
  - The income statement and balance sheet: revenue, results, depreciation, interest expense, interest-bearing debt (long- and short-term), cash, equity and total assets.
  - Living, commercial and total area, plus land tenure (owned land or *tomträtt*).
- **Calculates its own KPIs:** net debt, average interest rate, interest coverage, the share of loans due within a year, and debt per m² when the area is known. When a figure printed in the report disagrees with Boster's own calculation, the value is flagged.
- **Rates risk with rules:** each indicator is rated *Låg*, *Måttlig* or *Hög risk*, with its threshold shown next to the rating. The overall rating needs several warning signs and never rests on a single figure. You can change every threshold in [backend/config/risk_rules.toml](backend/config/risk_rules.toml).
- **Shows trends** over time. A year with no data stays empty in the chart and is never filled in by interpolation.
- **Quotes the report on maintenance and loans:** verbatim passages that mention pipe replacement, roof, façade, windows, elevators, fee changes, loans and auditor remarks, each with its page number. Boster does not interpret these passages.
- **Compares cooperatives:** tick 2–4 cooperatives on the dashboard and choose *Jämför*. Each cooperative's latest year is shown side by side, with every cell coloured by its risk rating; cooperatives are not ranked. For each key figure there is a bar chart of the latest year and a line chart over time. The page warns when the compared fiscal years differ, when a fiscal year isn't 12 months (that affects annual amounts but not per-m² figures), and when figures are missing. Debt per m² of total area and debt per m² of tenant-owned area are always separate rows. The selection is kept in the URL (`/jamfor?ids=1,3`), so it can be bookmarked.
- **Lets you correct values:** mark an extracted value as checked, or enter your own. Your value takes precedence, and the original stays visible as a source.

### Value statuses

Every value has one of these statuses, and the UI always shows which:

| Status (UI) | Meaning |
|---|---|
| Från dokument | Read automatically from a document, not checked |
| Kontrollerad | You checked it against the source |
| Manuellt angiven | You entered it |
| Beräknad | Calculated by Boster (the formula and inputs are shown) |
| Motstridiga uppgifter | Sources, or a source and the calculation, disagree. All candidates are kept |
| Saknas | Not available |

## Running locally

Requirements: Python 3.12 or later and Node.js 20 or later.

### 1. Backend (FastAPI)

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate          # Windows (Git Bash: source .venv/Scripts/activate)
# source .venv/bin/activate     # macOS/Linux
pip install -e ".[dev]"
cp .env.example .env            # then fill in API keys (optional for now)
uvicorn app.main:create_app --factory --reload
```

The API runs on <http://127.0.0.1:8000>, with interactive docs at <http://127.0.0.1:8000/docs>.

### 2. Frontend (React + Vite)

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>. The dev server forwards `/api` calls to the backend. To use a backend on another address, set `BOSTER_API_URL`.

### 3. Tests

```bash
cd backend
python -m scripts.download_samples   # once: fetches the sample annual reports (not stored in git)
python -m pytest
```

The regression tests compare extraction results with values checked by hand in five real annual reports. Without the samples, those tests are skipped and the rest still run.

## Configuration

Settings come from environment variables or `backend/.env`. The `.env` file is ignored by git, and keys are never sent to the browser or written to logs.

| Variable | Purpose |
|---|---|
| `TRAFIKLAB_API_KEY` | Public transport data (step 3 onwards) |
| `ANTHROPIC_API_KEY` | AI summaries (step 4). The app works without it |
| `DATA_DIRECTORY` | Location of the database and uploaded PDFs (default: `backend/data`) |

Risk thresholds are in [backend/config/risk_rules.toml](backend/config/risk_rules.toml). Restart the backend after editing the file.

## Your data

All data stays on your computer: a SQLite database and the uploaded PDFs, both in `backend/data/`. Deleting a cooperative or document in the app also deletes its figures and the PDF. To start over, delete `backend/data/`.

## Project structure

```
backend/
  app/
    domain/       Pure logic: metric catalogue, KPI formulas, conflict resolution, risk rules
    documents/    PDF reading: positioned rows, year-column tables, annual-report extraction
    services/     Document ingestion and the cooperative analysis
    api/          FastAPI routes
    models.py     Database tables     schemas.py  API models     config.py  Settings
  config/         risk_rules.toml
  scripts/        download_samples, inspect_report (print what is extracted from a PDF), dump_rows
  tests/
frontend/
  src/
    pages/        Dashboard, CooperativePage, ComparisonPage
    components/   Uploader, value details dialog, charts, badges
    api.ts        Typed API client      format.ts  Swedish formatting and labels
specs/spec.md     Product specification
```

## Design decisions

- **Structured observations are the source of truth, not text.** Each figure is stored as its own row in `financial_observations`, with its metric, fiscal year, value, unit, document, page, the label as printed in the report, the extraction method and its status. Summaries (step 4) will be generated from these rows, never the other way round.
- **KPIs are calculated in code, not by AI.** The formulas are in [backend/app/domain/kpis.py](backend/app/domain/kpis.py) and covered by unit tests. A missing input or a zero denominator gives "Saknas" with the reason, never an estimate.
- **The denominator is part of the metric.** Debt per m² of total area and debt per m² of tenant-owned area are separate metrics, so they can't be compared by mistake.
- **Conflicts are shown, not resolved silently.** Disagreeing sources are all kept and the value is marked as conflicting until you decide. Söderbysjön's report, for example, gives two different living areas.
- **PDF tables are read by position.** Each number is matched to the year column above it. This handles thousands separators split across words, note references and empty cells. Pages are classified by content (income statement, balance sheet, cash flow), because some reports have no section headings.
- **Extraction is conservative.** A value is extracted only when its row label matches a known pattern. Template quirks are handled explicitly: some report templates print `0` for key figures that weren't yet mandatory, and Boster treats that as "not reported" and shows a warning.
- **Uploaded and downloaded documents are untrusted.** Only PDFs are accepted, within a size limit, and nothing in them is executed. Links to local network addresses are refused.

## Known limitations

- **No OCR yet.** Scanned PDFs, such as many economic plans (*ekonomiska planer*), are detected and flagged, but no figures are read from them.
- **The total area is often missing.** Many reports state areas in formats that Boster doesn't recognise yet. Enter the area by hand (click the value, or *Ange* under *Fullständighet*) to enable the per-m² calculations.
- **HSB cooperatives' cash looks too low.** HSB cooperatives keep most of their cash in an account held by HSB, which the report lists as a receivable. Their *Kassa och bank* figure is therefore small.
- **Listing import is not built yet.** Fetching listings from Hemnet and Booli will often be blocked. The planned fallbacks are pasting the listing text or entering the details by hand, and the app will not try to get around access restrictions.
- **Single user, no login.** The app is meant to run locally. User accounts are needed before hosting it anywhere.
