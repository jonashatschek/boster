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
- **Browser constraints:** anything added to `backend/app` must work under Pyodide (no native-only packages, no network calls). The only outside calls are the public transport lookup, made by the frontend (`frontend/src/transport/runLookup.ts`) to Nominatim, Trafiklab ResRobot and Valhalla; the backend says which request to make and parses the raw responses as untrusted input. The app holds no secrets: a Trafiklab key is the visitor's own, kept in their browser's localStorage and never exported.
- Uploaded PDFs and imported files are untrusted input.
- **No personal data in the repo.** The repo is public. Never put a real person's name, phone number, email, personal identity number, signature or similar into code, tests, fixtures, docs, commit messages or issues, even when it comes from a pasted listing or a real report. Replace it with a placeholder such as `[Mäklarens namn]` before saving, and tell the user what was removed. This applies to private people, such as agents, board members, auditors and sellers. Companies' and cooperatives' names and organisation numbers are public and may stay. If you're unsure whether something is personal data, ask before saving it.

## How to work

- **Clarify before building.** If a requirement is ambiguous and the spec, README or code doesn't answer it, ask before writing code. Never guess a domain rule (what counts as missing, how a figure is classified, what the UI should say). State any assumption you do make.
- **Test first for backend logic.** Write a failing pytest, run it and see it fail for the right reason, then write the minimal code to pass, then refactor with tests green. A bug fix starts with a test that reproduces the bug.
- **Frontend has no test runner yet.** Verify UI changes with `npm run lint`, `npx tsc -b` and by running the app and checking the actual flow in the browser.
- **No "done" without evidence.** Run the checks and report the results. Say explicitly what you could not verify.
- **Keep scope tight.** Do what was asked; propose an issue for anything else you notice.
- For a whole issue, the user runs `/feature <n>` (`.claude/skills/feature/SKILL.md`), which walks through these steps.

## Working conventions

- **Todos live in GitHub Issues** (`gh issue list`, `gh issue view <n>`), grouped by milestone per roadmap step. When you find out-of-scope work, propose an issue instead of doing it. Reference the issue in commits (`Fixes #12`). The repo is public: keep issues free of personal data.

- When changing extraction, add or update a test with values checked by hand against the real PDF.
- Update the README status table / "What it does today" when a feature lands.
- Small commits with descriptive English messages, like the existing history.
