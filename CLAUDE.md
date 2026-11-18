# Boster

Evaluates Swedish apartments (bostadsrätter) and their housing cooperatives from annual-report PDFs and pasted listings. The FastAPI backend in `backend/app` runs **in the browser** via Pyodide in a Web Worker; there is no server. Full context: `README.md` (features, design decisions, structure) and `specs/spec.md` (product spec). Read the relevant section before changing behaviour.

## Commands

Backend (from `backend/`, venv at `backend/.venv`):
- Tests: `.venv/Scripts/python.exe -m pytest -q` (~20s). One file: `... -m pytest tests/test_kpis.py -q`
- Inspect what is extracted from a PDF: `.venv/Scripts/python.exe -m scripts.inspect_report <pdf>`
- Sample reports live in `sample_documents/` (gitignored; fetch with `python -m scripts.download_samples`). Without them the regression tests skip.

Frontend (from `frontend/`):
- Dev server: `npm run dev` → http://localhost:5173 (first load downloads Pyodide, ~15 MB)
- Lint: `npm run lint` · Typecheck: `npx tsc -b` · Build: `npm run build`

CI (`.github/workflows/deploy.yml`) runs pytest, lint and build, then deploys to GitHub Pages on push to `main`.

## Rules that are easy to get wrong

- **Never estimate, infer or interpolate a value.** Missing → "Saknas" with a reason. A balcony/elevator is recorded only if the listing states it. Chart gaps stay empty.
- **KPIs are computed in code** (`backend/app/domain/kpis.py`) with unit tests, never by AI.
- **Keep provenance.** Every extracted value keeps its source (document, page, printed label, or the listing line). Don't add a value without it.
- **Conflicts are kept, not resolved.** Disagreeing sources → status "Motstridiga uppgifter", all candidates stored.
- **User corrections win** and must never be overwritten by re-extraction.
- **Denominators are part of the metric.** Debt per m² total area ≠ debt per m² tenant-owned area; never merge them.
- **Extraction is conservative:** only extract when a row label matches a known pattern. New report template quirks get explicit handling plus a regression test.
- **Cooperatives are identified by organisation number**, and names only link on exact match (similar names are suggested, never merged).
- **Language:** UI text in Swedish; code, comments, docs and commit messages in English.
- **Browser constraints:** the app can't fetch other websites or hold secrets; anything added to `backend/app` must work under Pyodide (no native-only packages, no network calls).
- Uploaded PDFs and imported files are untrusted input.

## Working conventions

- When changing extraction, add or update a test with values checked by hand against the real PDF.
- Update the README status table / "What it does today" when a feature lands.
- Small commits with descriptive English messages, like the existing history.
