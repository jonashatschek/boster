# Boster

A personal web app for evaluating apartments for sale in Sweden (*bostadsrätter*) and the housing cooperatives (*bostadsrättsföreningar*) that own the buildings.

Upload a cooperative's annual report (*årsredovisning*) as a PDF. Boster reads the key figures and financial statements, calculates its own KPIs, rates the main financial risks with documented rules, and shows where every number came from, down to the page in the PDF.

Boster runs entirely in the browser. It is a static website with no server and no database to set up: the Python analysis code runs in the visitor's browser with [Pyodide](https://pyodide.org), PDFs are read with [pdf.js](https://mozilla.github.io/pdf.js/), and each visitor's data is saved in their own browser. Nothing is uploaded anywhere, except an apartment's address when its nearby public transport is looked up.

The user interface is in Swedish. Code and documentation are in English.

The full product specification is in [specs/spec.md](specs/spec.md).

## Status

| Step | Content | Status |
|---|---|---|
| 1 | Domain model, KPI formulas, risk rules, PDF extraction, tests | Done |
| 2 | Upload a report → cooperative page with KPIs, charts, sources and manual corrections | Done |
| 2b | Compare 2–4 cooperatives side by side | Done |
| 3 | Import a listing (pasted text or manual entry) → property page linked to a cooperative | Done |
| 3b | Runs in the browser as a static site; export and import of all data | Done |
| 4 | Swedish AI summaries with links to the evidence | Next (needs a way to call an AI model without a server holding the key) |
| 5 | Comparing properties side by side, and saved comparisons | Compare side by side: done. Saved comparisons: planned |
| 5b | Public transport: walking distance to the nearest tunnelbana, pendeltåg/lokaltåg and bus stop | Done |

## What it does today

### Apartments

- **Add a listing** by pasting its text: open the listing on Hemnet, Booli or the agent's site, press Ctrl+A, Ctrl+C, and paste it into Boster. You can also save the listing's link, so you can find your way back. Boster never fetches the link: a website in the browser can't read other websites, and Hemnet and Booli block automated fetching anyway.
- **Reads the facts:** address, area, price, number of rooms, monthly fee and what it includes, floor, elevator, balcony, construction year, energy class, cooperative and publication date. Each value keeps the line of listing text it came from. A balcony or elevator is recorded only when the listing states it, never inferred.
- **Never estimates the price.** A missing price shows as "Saknas".
- **Your corrections are kept.** Values you edit or mark as checked are never overwritten when the listing is read again.
- **Links to the cooperative** automatically, but only on an exact name match ("BRF Segelflygaren" = "HSB Bostadsrättsförening Segelflygaren i Stockholm", while "Byamännen" ≠ "Byamännen 2"). Similar names are suggested for you to confirm. A report uploaded later links any waiting listings with a matching name.
- **Calculates** price per m², annual fee per m², the apartment's approximate share of the cooperative's loans, and the possible fee increase if interest rates rise by one percentage point. The formula and inputs are shown for each.
- **Shows the agent's description verbatim** and marks it as claims, not facts.
- **Shows public transport nearby:** the nearest tunnelbana, pendeltåg/lokaltåg and bus stop, with the walking distance and time there. The address is looked up in OpenStreetMap ([Nominatim](https://nominatim.org)), the stops come from Trafiklab's [ResRobot](https://www.trafiklab.se/api/our-apis/resrobot-v21/), and the walking route from OpenStreetMap's routing service ([Valhalla](https://valhalla1.openstreetmap.de)). For each type, the stop nearest in a straight line is routed; a type with no stop within 2 km on foot is left out of the list (in the comparison it shows as "Saknas" with the reason), never replaced by an estimate. The walking time is the routing service's, not a guess. It runs automatically when the property page opens, and again when the address changes (a result for an old address is marked as such). If OpenStreetMap only knows the street, not the house number, no distances are shown, since on a long street they could be far off; the page asks you to check the address. **You choose the address when it is ambiguous:** if the listing names no municipality, or the street and number aren't found exactly once in it, the apartment page first shows the matching addresses from OpenStreetMap (e.g. "Pilotgatan 16, Bagarmossen, Stockholms kommun" and "… Uppsala kommun") and Boster never picks for you. Your choice sets the municipality, marked as entered by you with OpenStreetMap as the source. You can also type the municipality yourself, or continue without public transport (remembered for that address). The site uses one shared Trafiklab key (ResRobot v2.1), set when it is built (see Publishing). "Pendeltåg/lokaltåg" is Trafiklab's local-train class, which also includes e.g. Roslagsbanan and Saltsjöbanan. The comparison shows the nearest stop of each type too.
- **Compares apartments:** tick 2–4 apartments on the dashboard and choose *Jämför*. The apartments are shown side by side, grouped into the apartment itself, location, features, the cooperative (its 0–100 score with its coverage, and each risk-rated key figure for its latest year), estimates and maintenance. Every value keeps its status badge and its source (the listing line, the formula, or the report page); missing values show as "Saknas" with the reason, never as zero. The loan share and the possible fee increase are marked as estimates, and the page warns when they rest on different debt measures (per m² of total area vs. tenant-owned area). Maintenance shows which topics the cooperative's reports mention, with page numbers, and the quotes on request. Apartments are not ranked. The selection is kept in the URL (`#/jamfor/bostader?ids=1,3`).

### Cooperatives

- **Add documents** by drag and drop or file picker. The PDF is read in the browser and stays there. Adding the same file twice reuses the stored copy.
- **Identifies the cooperative** by its organisation number. Cooperatives with similar names are never merged. If a document ends up under the wrong cooperative, you can move it.
- **Reads figures from the report:**
  - The multi-year overview (*flerårsöversikt*), including the key figures required since 2023: debt per m², savings per m², interest sensitivity, energy cost per m², fee per m², and the fee share of revenue.
  - The income statement and balance sheet: revenue, results, depreciation, interest expense, interest-bearing debt (long- and short-term), cash, equity and total assets.
  - Living, commercial and total area, plus land tenure (owned land or *tomträtt*).
- **Calculates its own KPIs:** net debt, average interest rate, interest coverage, the share of loans due within a year, and debt per m² when the area is known. When a figure printed in the report disagrees with Boster's own calculation, the value is flagged.
- **Rates risk with rules:** each indicator is rated *Låg*, *Måttlig* or *Hög risk*, with its threshold shown next to the rating. **A score from 0 to 100** sums them up: each of the six rated key figures gets 0–100 points on a gradual scale between its two thresholds (100 on the good side of the *Låg risk* limit, 0 at the *Hög risk* limit), and the score is their weighted average. The weights and their reasons are shown with the score. A missing or conflicting figure is left out and the others weigh more, and the page says what was included and what was missing ("Baserat på 4 av 6 nyckeltal (75 % av vikten)"); below 3 key figures or half the weight there is no score, only *Otillräcklig information*. The score is shown in neutral colours and is not a credit rating. On the cooperative page it always comes with its explanation (coverage and missing figures, and under *Så räknas poängen* each figure's value, source, scale, points, weight and contribution); the overview lists, the apartment page and the comparisons show the number and lead to that explanation. It replaced the earlier overall rating. You can change every threshold and weight in [backend/config/risk_rules.toml](backend/config/risk_rules.toml).
- **Shows trends** over time. A year with no data stays empty in the chart and is never filled in by interpolation.
- **Quotes the report on maintenance and loans:** verbatim passages that mention pipe replacement, roof, façade, windows, elevators, fee changes, loans and auditor remarks, each with its page number. Boster does not interpret these passages.
- **Compares cooperatives:** tick 2–4 cooperatives on the dashboard and choose *Jämför*. Each cooperative's latest year is shown side by side, with every cell coloured by its risk rating and each cooperative's 0–100 score (linking to its explanation) in its column heading; cooperatives are not ranked or sorted by the score. For each key figure there is a bar chart of the latest year and a line chart over time. The page warns when the compared fiscal years differ and when a fiscal year isn't 12 months (that affects annual amounts but not per-m² figures). Missing figures show as "Saknas" in the table, never as zero; each of the 12 core key figures always has a row, even when none of the compared cooperatives reports it. Hovering "Saknas" shows why, from the data only: the figure wasn't found in that year's report, and if Boster can calculate it, which inputs are missing or have conflicting sources. Debt per m² of total area and debt per m² of tenant-owned area are always separate rows. The selection is kept in the URL (`#/jamfor?ids=1,3`), so it can be bookmarked.
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

## Your data

Each visitor's data (a SQLite database and their PDFs) is saved in their own browser, in IndexedDB. It is never sent anywhere, and other visitors can't see it. The one exception is the public transport lookup: it sends the apartment's address (street, number and municipality) to OpenStreetMap and its coordinates to Trafiklab and OpenStreetMap's routing service. The page says so.

- **Exportera** (top right) downloads everything as a zip file: the database and the PDFs.
- **Importera** replaces everything in this browser with an exported file. Use it to move to another computer or browser, to restore a backup, or to share your analysis with someone.
- Clearing the browser's site data deletes everything, so export now and then to keep a copy. Boster asks the browser to keep the data even when disk space runs low, but not every browser agrees.
- Deleting a cooperative or document in the app also deletes its figures and the PDF. On the overview, the × on a row deletes that apartment or cooperative, and *Ta bort alla* deletes every item in that list (apartments are kept, unlinked, when their cooperative is deleted). Both ask first; nothing can be undone, so export before if you want a copy. The checkboxes only select items for comparison (*Avmarkera* unticks them).

## Publishing

The site is published to GitHub Pages by [.github/workflows/deploy.yml](.github/workflows/deploy.yml) on every push to `main`, after the tests pass. To set it up once: on GitHub, open the repository's **Settings → Pages** and set **Source** to **GitHub Actions**. The site is then at `https://<user>.github.io/boster/`.

The public transport lookup needs a Trafiklab key with access to **ResRobot v2.1** (free from [trafiklab.se](https://www.trafiklab.se)). Add it under **Settings → Secrets and variables → Actions → Variables** as `TRAFIKLAB_API_KEY`; the workflow passes it to the build as `VITE_TRAFIKLAB_API_KEY`. For `npm run dev`, put `VITE_TRAFIKLAB_API_KEY=<key>` in `frontend/.env` (ignored by git). Without a key the site works, and the transport section says the key is missing.

`npm run build` in `frontend` produces a static site in `frontend/dist` that any static host can serve, such as Netlify or Cloudflare Pages. Visitors' browsers load Pyodide from the jsDelivr CDN and one small package (python-multipart) from PyPI.

## Development

Requirements: Node.js 20 or later, and Python 3.12 or later for the tests.

### Run the app

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>. The Python code in `backend/app` is bundled into the browser's Web Worker; after changing it, reload the page. The first start downloads Python (about 15 MB, cached by the browser afterwards).

### Tests

The backend tests run on a normal desktop Python, where PyMuPDF stands in for pdf.js. All commands start from the `backend` folder.

**Windows PowerShell**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
python -m scripts.download_samples   # once: fetches the sample annual reports (not stored in git)
python -m pytest
```

If PowerShell refuses to run `Activate.ps1`, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once.

**macOS/Linux or Git Bash**

```bash
python -m venv .venv
source .venv/bin/activate       # Git Bash on Windows: source .venv/Scripts/activate
pip install -e ".[dev]"
python -m scripts.download_samples
python -m pytest
```

The regression tests compare extraction results with values checked by hand in real annual reports. Without the samples, those tests are skipped and the rest still run. On the seven sample reports, pdf.js in the browser gives the same figures as PyMuPDF, except in two cases where pdf.js is right and PyMuPDF is not: it keeps a raised footnote marker apart from a number, and it finds one area PyMuPDF misses.

Risk thresholds are in [backend/config/risk_rules.toml](backend/config/risk_rules.toml).

## How it works

```
Browser tab                                   Web Worker
  React pages ── api.ts ── pythonFetch ──────▶  Pyodide (Python 3.14)
  pdf.js reads an uploaded PDF's words           FastAPI app (backend/app), called over ASGI
  and positions before it is sent                SQLite + PDFs in /data ◀──▶ IndexedDB
```

The frontend calls the same `/api/...` routes as before, but [frontend/src/python/client.ts](frontend/src/python/client.ts) hands each request to a Web Worker instead of the network. The worker runs the unchanged FastAPI app through [backend/app/browser.py](backend/app/browser.py), and saves the data directory to IndexedDB after every change.

## Project structure

```
backend/
  app/
    domain/       Pure logic: metric catalogue, KPI formulas, conflict resolution, risk rules
    documents/    PDF text to positioned rows, year-column tables, annual-report extraction
    listings/     Listing import: text label/value extraction
    transport/    Public transport: queries and parsing of Nominatim, ResRobot and Valhalla responses
    services/     Document ingestion, cooperative analysis, export and import
    api/          FastAPI routes
    browser.py    Entry point for the browser (Pyodide)
    models.py     Database tables     schemas.py  API models     config.py  Settings
  config/         risk_rules.toml
  scripts/        download_samples, inspect_report (print what is extracted from a PDF), dump_rows
  tests/
frontend/
  src/
    pages/        Dashboard, PropertyPage, CooperativePage, ComparisonPage, PropertyComparisonPage
    components/   Uploader, value details dialog, charts, badges, export/import
    python/       Web Worker running Pyodide, and the client that talks to it
    pdf/          Reading page text with pdf.js
    transport/    Makes the public transport requests the backend asks for
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
- **Uploaded documents and imported files are untrusted.** Only PDFs are accepted, within a size limit, and nothing in them is executed. An import must contain exactly the files an export writes, and its database is checked before it replaces anything.
- **The analysis runs in the browser, not on a server.** That makes the site free to host, keeps each visitor's data private without accounts, and means there is no server to maintain. The price is a slower first visit (Python is downloaded once) and no fetching of web pages.
- **The Python code makes no network calls.** For the public transport lookup it tells the page which request to make next; the page makes it and hands back the raw response, which Python parses as untrusted input and stores with the address it was looked up with and the retrieval date. The page only calls the three known services, and adds the site's Trafiklab key itself, so the key never enters the database or an export. The key is shared by all visitors and readable in the built site, as it must be for a browser to call Trafiklab; it is not treated as a secret, but it is kept out of git (a repository variable) so it can be changed without a commit.

## Known limitations

- **No OCR yet.** Scanned PDFs, such as many economic plans (*ekonomiska planer*), are detected and flagged, but no figures are read from them.
- **The total area is sometimes missing.** Boster reads areas from running text (e.g. "Total bostadsarea 15 575 m²", "BOA/LOA"), from "Bostadsyta | Lokalyta | Totalyta" tables, and from HSB's object table ("Antal | Benämning | m2", whose "Totalt … objekt" row is the total area the report uses for its key figures; rows are never added together). Other formats aren't recognised yet. Enter the area by hand (click the value, or *Ange* under *Fullständighet*) to enable the per-m² calculations.
- **HSB cooperatives' cash looks too low.** HSB cooperatives keep most of their cash in an account held by HSB, which the report lists as a receivable. Their *Kassa och bank* figure is therefore small.
- **Listings must be pasted.** The text extractor is tested on the layouts Hemnet, Booli and agents' sites produce when copied, but a site redesign can break it. Missing fields are listed so you can fill them in.
- **Public transport covers only the nearest stop of each type.** It doesn't rank stops by how useful their connections are, show departures, or give travel times to a destination. The stop nearest in a straight line is the one routed, so in rare cases another stop could be closer on foot. Trams, regional trains and ferries are not shown.
- **Data lives in one browser.** There are no accounts and no sync. Use export and import to move data between devices.
- **The first visit is slow.** Starting Python takes 10–20 seconds the first time; later visits use the browser's cache.
