# Apartment Analysis — Product Specification

## 1. Overview

Build a personal web application that helps a user evaluate, analyze, and compare apartments for sale in Sweden.

The application accepts links to apartment listings from property websites such as Booli, Hemnet, and real estate agencies. It extracts relevant information, analyzes the associated housing cooperative (bostadsrättsförening), and presents the results in a structured, transparent, and comparable format.

Users must also be able to upload or link annual reports and other documents relating to housing cooperatives.

AI may be used to extract information from unstructured text, summarize documents, and explain financial risks. All important factual claims must be traceable to source material or explicitly marked as estimates.

The application is primarily intended for personal use.

## 2. Product goals

1. Quickly understand the most important characteristics of an apartment listing.
2. Identify financial risks and strengths in a housing cooperative.
3. Reduce the time required to read and understand annual reports.
4. Compare two or more apartments using consistent metrics.
5. Save analyzed apartments and housing cooperatives for later review.
6. Make it easy to distinguish verified facts, calculated metrics, estimates, and AI-generated interpretations.

### Non-goals for the initial release

- Automated bidding or purchase recommendations.
- Predicting future apartment prices.
- Replacing professional financial or legal advice.
- Automatically monitoring every property website.
- Automated account creation or login to third-party websites.
- Building a comprehensive property valuation model.

## 3. Target user and primary workflow

The user discovers an interesting apartment on Booli, Hemnet, or an estate agent's website.

The user copies the listing URL and pastes it into the application.

The application then:

1. Retrieves the available listing information.
2. Extracts structured property data.
3. Identifies the housing cooperative, where possible.
4. Retrieves or requests the relevant cooperative documents.
5. Calculates relevant financial metrics.
6. Generates an evidence-based summary.
7. Displays the results on a property analysis page.
8. Allows the user to save the apartment and compare it with other saved properties.

If information cannot be retrieved automatically, the application must allow the user to upload documents or manually enter missing information.

## 4. Functional requirements

### FR-01: Import an apartment listing

The user must be able to submit a property listing URL.

Initially supported URL sources should include:

- Booli
- Hemnet
- Swedish estate agent websites

The application must validate submitted URLs and handle unsupported sources gracefully.

The application should use source-specific extraction adapters where appropriate. It must not assume that all websites have the same HTML structure.

If automated retrieval fails because of access restrictions, unavailable content, or unsupported page structures, the application must explain the limitation and offer manual input or document upload.

The application must not attempt to bypass authentication, CAPTCHAs, or technical access restrictions.

### FR-02: Property information extraction

Extract the following fields when available:

- Listing title
- Listing URL and source
- Address
- Municipality and neighborhood
- Apartment size in square metres
- Number of rooms
- Floor
- Elevator availability
- Balcony, terrace, or patio
- Asking price
- Monthly association fee (månadsavgift)
- Fee inclusions, such as heating, water, and broadband
- Construction year
- Renovation information
- Energy performance, where available
- Listing description
- Listing publication date, where available
- Housing cooperative name
- Listing images or image URLs, where permitted

Every field must support missing values.

Do not infer that an apartment has a balcony, elevator, or another feature simply because it is common for similar properties.

### FR-03: Asking price and estimated price

The application must distinguish between:

- Verified asking price
- User-entered price
- Estimated price range
- Unknown price

When an asking price is available, display it as the asking price.

When the asking price is unavailable, the application may calculate an estimated range using available comparable properties and other relevant data.

An estimate must:

- Be clearly labelled as an estimate.
- Display the lower and upper bounds.
- Include the estimation method.
- Display the date of the estimate.
- Explain the most important assumptions.
- Indicate data quality and confidence where possible.

The application must never present an estimated price as an asking price.

If there is insufficient comparable data, display "Insufficient data to estimate price" instead of inventing a range.

### FR-04: Listing description analysis

Analyze the property description and produce a concise Swedish summary.

The summary should identify:

- Main selling points
- Renovations and upgrades mentioned
- Potential maintenance concerns
- Unclear or ambiguous statements
- Important information that appears to be missing
- Claims that should be verified before purchase

The application should distinguish factual statements from interpretations.

For example, "newly renovated kitchen" should be reported as a claim made in the listing unless independent evidence confirms it.

The application must not assume that marketing language proves the quality, age, or condition of a renovation.

### FR-05: Public transport and location

Identify relevant nearby public transport options.

For each relevant stop or station, display:

- Name
- Transport type, such as metro, commuter train, tram, bus, or regional rail
- Approximate walking distance
- Approximate walking time
- Data source and retrieval date, where available

Prioritize useful connections and nearby stations rather than simply reporting the geographically closest stop.

Where reliable routing and timetable data are available, optionally show travel time to a configurable destination.

Do not fabricate distances, walking times, or service frequencies. If routing information is unavailable, explain that the location analysis is incomplete.

### FR-06: Housing cooperative identification

Identify the housing cooperative associated with the apartment.

Display its name and relevant identifying information.

Avoid merging two cooperatives with similar names. Use organisation number (organisationsnummer) as the primary identifier whenever available.

A user must be able to correct an incorrect cooperative match.

The same cooperative should be reusable across multiple property analyses.

### FR-07: Upload and analyze cooperative documents

Users must be able to upload PDF documents, including:

- Annual reports
- Financial statements
- Maintenance plans
- Renovation information
- Other documents relevant to the cooperative

Users must also be able to submit a direct document URL when accessible.

The application should extract text and tables from PDFs where possible. Scanned documents should be handled using OCR when supported.

The application must identify the document type and reporting period when possible.

For annual reports, extract the following information when available:

- Reporting year
- Annual revenue
- Operating costs
- Operating result
- Financial result
- Annual result
- Total assets
- Total liabilities
- Interest-bearing debt
- Cash and cash equivalents
- Short-term liabilities
- Long-term liabilities
- Interest expense
- Interest rates and loan maturity dates, if disclosed
- Property tax and ground rent (tomträtt), if relevant
- Planned maintenance and major completed renovations
- Information about pipe replacement (stambyte), façade, roof, windows, elevators, drainage, and other major building components
- Information about future borrowing or fee increases
- Auditor's remarks and significant disclosures
- Whether the land is owned or leased

The application must not assume that missing information means that a renovation has not occurred.

### FR-08: Cooperative financial KPIs

Calculate the following metrics when sufficient source data is available:

**Debt and financial exposure**

- Interest-bearing debt per square metre of residential area
- Interest-bearing debt per square metre of total area, when available
- Total interest-bearing debt
- Cash and cash equivalents
- Net debt, when the calculation is appropriate and the relevant data is available
- Average interest rate, where sufficient loan data exists
- Interest coverage or another clearly defined measure of the ability to cover interest expenses

**Operations and revenue**

- Annual fee revenue
- Operating costs
- Annual result
- Operating cash flow, only when the necessary information is available
- Fee per square metre per year, where the relevant area and fee data are available
- Historical changes in fees
- Historical changes in debt

**Long-term financial sustainability**

- Maintenance needs and disclosed funding plans
- Loan maturities and refinancing exposure
- Exposure to interest rate increases
- Potential future fee increases
- Dependence on rental income or other non-fee revenue
- Land ownership versus leasehold
- Liquidity and short-term financial obligations

For every KPI, document:

- Formula
- Required input data
- Units
- Reporting period
- Source references
- Whether the value is reported, calculated, estimated, or unavailable

Do not compare values with different denominators as if they were equivalent. For example, debt per square metre of residential area must not be directly compared with debt per square metre of total area without a clear warning.

### FR-09: Cooperative financial assessment

Generate a concise Swedish-language assessment containing:

1. Overall financial situation
2. Main financial strengths
3. Main financial risks
4. Debt and interest-rate exposure
5. Maintenance and renovation situation
6. Potential pressure on monthly fees
7. Missing information and recommended follow-up questions

Use descriptive risk categories:

- Low concern
- Moderate concern
- High concern
- Insufficient information

These categories must be supported by documented rules and evidence. They must not be presented as an objective credit rating.

Avoid relying on a single KPI to determine the overall assessment.

A cooperative may also get a score from 0 to 100 (decided by the owner in #11). It is the weighted average of part scores computed in code from documented, configurable rules, and it is only ever shown together with its full breakdown: each part's value, source, rule, part score and weight, and which parts are missing and why. A missing part is left out and the remaining weights are scaled up; no value is invented for it. Below a minimum coverage there is no score. The score must not replace the explanation of the financial risks, and must not be presented as an objective credit rating.

Where possible, distinguish between:

- Actual historical financial performance
- Current financial exposure
- Disclosed future commitments
- Risks that are plausible but not confirmed

### FR-10: Historical financial trends

When multiple annual reports are available, build a time series of important financial metrics.

At minimum, support:

- Debt per square metre
- Total interest-bearing debt
- Annual result
- Annual fee revenue
- Monthly fee changes, where known
- Interest expense
- Cash and cash equivalents

Display charts where historical data is available.

The user must be able to see the reporting year for every data point.

Missing years must not be interpolated and displayed as actual figures.

### FR-11: Compare apartments

Allow the user to select two or more saved apartments for comparison.

Display a side-by-side comparison of:

- Asking price or estimated price
- Price per square metre
- Apartment size
- Number of rooms
- Monthly fee
- Construction year
- Location
- Public transport access
- Relevant features
- Cooperative name
- Cooperative financial KPIs
- Renovation history and upcoming maintenance risks

Clearly distinguish missing data from zero values.

Where estimates are used, indicate that the comparison is based on estimates rather than verified figures.

### FR-12: Compare housing cooperatives

Allow the user to compare two or more cooperatives independently of specific apartment listings.

Include:

- Debt per square metre, with the denominator specified
- Total debt
- Cash and cash equivalents
- Annual results and revenue
- Interest expenses
- Fee trends
- Land ownership
- Major renovation history
- Known maintenance needs
- Loan maturity and refinancing exposure, where available
- Data completeness and reporting periods

Display charts for comparable historical metrics where possible.

Warn the user when reporting periods, definitions, or source quality differ.

### FR-13: Visualizations

Use visualizations when they make the information easier to understand.

Examples:

- Bar chart: debt per square metre across cooperatives
- Line chart: debt and annual results over time
- Line chart: monthly fees over time
- Comparison chart: asking price and price per square metre
- Table: major renovations and planned maintenance
- Indicator: completeness of available data

Every chart must include meaningful labels, units, and reporting periods.

Never show a numerical score without its explanation, and never use it as a substitute for explaining financial risks (see the 0–100 score under the risk categories above).

### FR-14: Save and manage analyses

Users must be able to:

- Save an apartment analysis.
- Revisit a previous analysis.
- Update an analysis when new information becomes available.
- Associate multiple apartments with the same cooperative.
- View documents associated with a cooperative.
- Delete saved apartments and analyses.
- Manually edit or correct extracted fields.

The application should retain the source URL, extraction timestamp, and document reporting period.

### FR-15: Sources and traceability

Every important factual claim must have traceable provenance.

For each extracted or calculated value, store where it came from, such as:

- Listing URL
- Document filename and page number
- Table or section, when identifiable
- External data provider
- Calculation based on other source values

AI-generated summaries should link to the underlying evidence wherever possible.

If a claim cannot be supported by available evidence, it must be labelled as unverified or omitted.

## 5. Data quality and calculation rules

The application must use a structured data model rather than treating the AI-generated summary as the source of truth.

Each extracted value should include:

- Field name
- Value
- Unit
- Source
- Reporting period or observation date
- Extraction method
- Confidence or verification status
- Optional explanatory notes

Use explicit statuses such as:

- Verified from source
- Extracted, not independently verified
- Calculated
- Estimated
- Missing
- Conflicting sources

When sources conflict, retain the conflicting values and explain the discrepancy rather than silently selecting one.

Calculations must be deterministic and covered by automated tests. AI must not independently calculate financial KPIs in free-form prose when the same result can be computed in application code.

For financial calculations, preserve the original reported figures and the inputs used for derived values.

## 6. Suggested data model

The implementation should include the following main entities:

### Property

- Id
- SourceUrl
- SourceName
- Address
- Municipality
- LivingArea
- NumberOfRooms
- Floor
- ConstructionYear
- AskingPrice
- MonthlyFee
- Description
- ListingDate
- HousingCooperativeId
- CreatedAt
- UpdatedAt

### HousingCooperative

- Id
- OrganisationNumber
- Name
- Address
- LandOwnershipType
- CreatedAt
- UpdatedAt

### SourceDocument

- Id
- HousingCooperativeId
- PropertyId, optional
- DocumentUrl, optional
- FileReference, optional
- DocumentType
- ReportingYear
- UploadedAt
- ExtractionStatus

### FinancialObservation

- Id
- HousingCooperativeId
- SourceDocumentId
- MetricName
- Value
- Unit
- ReportingPeriod
- SourcePage
- VerificationStatus

### PropertyAnalysis

- Id
- PropertyId
- Summary
- AnalysisVersion
- CreatedAt

### CooperativeAnalysis

- Id
- HousingCooperativeId
- Summary
- AnalysisVersion
- CreatedAt

### SavedComparison

- Id
- Name
- CreatedAt

Use appropriate relationships, database constraints, and indexes.

Avoid storing all extracted data solely in unstructured JSON. JSON may be used for supplemental extraction metadata, but important metrics must remain queryable.

## 7. User interface requirements

The interface must be simple, responsive, and primarily in Swedish.

### Dashboard

- URL input for adding a property
- Recently analyzed apartments
- Saved comparisons
- Recently analyzed cooperatives

### Property details page

- Property facts
- Asking price and price per square metre
- Description analysis
- Location and transport
- Cooperative summary
- Financial risk highlights
- Sources and missing information

### Cooperative details page

- Financial overview
- KPI table
- Historical charts
- Major renovations
- Maintenance concerns
- Source documents
- AI-generated assessment
- Data completeness indicators

### Comparison page

- Side-by-side property comparison
- Side-by-side cooperative comparison
- Charts for comparable metrics
- Explicit indicators for estimates and missing data

Avoid cluttering the interface with every extracted field by default. Prioritize important information and allow the user to inspect the underlying evidence when needed.

## 8. Technical architecture

Use a modular architecture with clear separation between:

- Frontend
- Application/API layer
- Domain and calculation logic
- Data persistence
- Property source adapters
- Document processing
- AI analysis
- External transport and geocoding services

The system should support multiple AI providers or models through an abstraction layer where practical.

AI prompts and output schemas should be versioned.

Use structured AI responses with schema validation rather than depending on arbitrary prose for data extraction.

External API keys must be stored securely on the server and never exposed to the browser. (Boster runs as a static site without a server. Its Trafiklab key is therefore shared and readable in the built site; it is set at build time from a repository variable and is not kept in git.)

Property websites and uploaded documents must be treated as untrusted inputs. Do not execute embedded content or allow instructions inside a document to override application behavior.

External data retrieval must include sensible timeouts, error handling, and caching.

## 9. Non-functional requirements

- The application must be usable on desktop and mobile.
- Financial calculations must be deterministic and testable.
- Missing data must not cause the application to crash.
- Failed extraction must produce a useful error message.
- Repeated analyses should reuse existing documents and extracted data where appropriate.
- External service failures must not invalidate previously saved analyses.
- Sensitive information and API credentials must not be written to application logs.
- Uploaded documents must be handled securely.
- The user must be able to delete saved data.
- The application must make clear when data was last retrieved.
- AI-generated output must be validated before being saved or displayed.

## 10. MVP scope

The first release should implement the following:

1. Submit a property URL.
2. Extract property data from supported and accessible pages.
3. Allow manual correction of extracted data.
4. Upload a housing cooperative annual report in PDF format.
5. Extract important financial information from the report.
6. Calculate a defined initial set of financial KPIs.
7. Generate a sourced Swedish summary of the apartment and cooperative.
8. Save properties and cooperatives.
9. Compare two properties.
10. Compare two cooperatives.
11. Display basic historical charts when multiple reporting years are available.
12. Show source references, uncertainty, and missing data.

Advanced price estimation, automated renovation-plan extraction, detailed public transport routing, and automatic monitoring should be implemented only after the core workflow is reliable.

## 11. Definition of done

The MVP is complete when:

- A user can submit a supported property URL and receive a structured analysis.
- A user can upload an annual report and receive an analysis of the available financial information.
- Every displayed KPI can be traced to source data or a documented calculation.
- Missing or conflicting data is handled explicitly.
- The same cooperative can be reused across multiple properties.
- Two properties and two cooperatives can be compared.
- Relevant historical charts display correctly.
- Automated tests cover KPI calculations, missing data, and conflicting source values.
- The application can run locally using documented setup instructions.
- The application does not present estimates as verified facts.

## 12. Implementation approach

Implement the application in small, independently testable increments.

Before writing production code:

1. Review the specification and identify ambiguities.
2. Propose an implementation plan.
3. Identify external dependencies and their limitations.
4. Define the domain model and core KPI formulas.
5. Write acceptance tests for the first vertical slice.
6. Document decisions that materially affect the architecture.

Do not implement the entire application in one step.

Prioritize a working end-to-end workflow over broad but unreliable extraction support.

When a requirement cannot be implemented reliably, document the limitation and propose a fallback rather than fabricating data.
