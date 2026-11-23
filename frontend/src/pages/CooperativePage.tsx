import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  api,
  ApiError,
  type CooperativeListItem,
  type CooperativeOverview,
  type DocumentSummary,
  type MetricDefinition,
  type MetricSeries,
  type YearValue,
} from '../api'
import { ConcernBadge } from '../components/Badges'
import { DocumentLink } from '../components/DocumentLink'
import { DocumentUploader } from '../components/DocumentUploader'
import { MaintenanceQuestions } from '../components/MaintenanceQuestions'
import { MetricChart } from '../components/MetricChart'
import { ScoreCard } from '../components/ScoreCard'
import { ValueDetails } from '../components/ValueDetails'
import {
  DOCUMENT_TYPE_LABELS,
  EXTRACTION_STATUS_LABELS,
  formatDate,
  formatValue,
  LAND_TENURE_LABELS,
} from '../format'

// Charts shown when at least two years of data exist, in this order.
const CHART_METRICS = [
  'debt_per_sqm_total_area',
  'savings_per_sqm',
  'annual_fee_per_sqm',
  'interest_sensitivity_pct',
  'result_after_financial_items',
  'interest_bearing_debt',
  'interest_expense',
  'energy_cost_per_sqm',
]

const TABLE_GROUPS: { category: MetricSeries['category']; title: string }[] = [
  { category: 'key_figure', title: 'Nyckeltal' },
  { category: 'base_figure', title: 'Resultat- och balansräkning' },
  { category: 'area', title: 'Ytor' },
]

const MAX_TABLE_YEARS = 6

interface Selection {
  metricKey: string
  fiscalYear: number
}

export function CooperativePage() {
  const id = Number(useParams().id)
  const navigate = useNavigate()
  const [overview, setOverview] = useState<CooperativeOverview | null>(null)
  const [definitions, setDefinitions] = useState<MetricDefinition[]>([])
  const [others, setOthers] = useState<CooperativeListItem[]>([])
  const [error, setError] = useState<string | null>(null)
  const [selection, setSelection] = useState<Selection | null>(null)

  const load = useCallback(() => {
    setError(null)
    api
      .getCooperative(id)
      .then(setOverview)
      .catch((caught) => setError(caught instanceof ApiError ? caught.message : 'Kunde inte hämta föreningen.'))
    api.listCooperatives().then((list) => setOthers(list.filter((c) => c.id !== id)))
  }, [id])

  useEffect(load, [load])
  useEffect(() => {
    api.listMetrics().then(setDefinitions)
  }, [])

  const metricLabels = useMemo(() => Object.fromEntries(definitions.map((d) => [d.key, d.label])), [definitions])

  if (error) return <div className="notice error">{error}</div>
  if (!overview) return <p className="muted">Laddar …</p>

  const { cooperative, risk, completeness } = overview
  const tableYears = overview.fiscal_years.slice(0, MAX_TABLE_YEARS)
  const charts = CHART_METRICS.map((key) => overview.metrics.find((m) => m.key === key)).filter(
    (m): m is MetricSeries => !!m && m.values.filter((v) => v.display_value !== null).length >= 2,
  )
  const messages = overview.documents.flatMap((d) => d.extraction_messages.map((m) => ({ document: d, message: m })))

  const selectedMetric = selection ? findSeries(overview, definitions, selection.metricKey) : null
  const selectedValue = selection && selectedMetric ? findValue(selectedMetric, selection.fiscalYear) : null

  async function deleteCooperative() {
    if (!confirm(`Ta bort ${cooperative.name} med alla dokument och värden? Det går inte att ångra.`)) return
    await api.deleteCooperative(cooperative.id)
    navigate('/')
  }

  return (
    <div className="stack" style={{ gap: '1.5rem' }}>
      <div className="small">
        <Link to="/">← Översikt</Link>
      </div>

      <CooperativeHeader overview={overview} onChange={setOverview} onDelete={deleteCooperative} />

      {messages.length > 0 && (
        <div className="stack">
          {messages.map(({ document, message }, index) => (
            <div className="notice warning" key={index}>
              <strong>{document.original_filename}:</strong> {message}
            </div>
          ))}
        </div>
      )}

      <section className="card">
        <h2>Riskbedömning {risk.fiscal_year && <span className="muted">({risk.fiscal_year})</span>}</h2>
        {overview.score ? (
          <ScoreCard score={overview.score} disclaimer={risk.disclaimer} />
        ) : (
          <p className="small muted">{risk.disclaimer}</p>
        )}
        <h3>Nyckeltal som bedöms</h3>
        <div className="risk-grid">
          {risk.indicators.map((indicator) => (
            <div className={`risk-card ${indicator.level}`} key={indicator.key}>
              <div className="spread">
                <span className="small muted">{indicator.label}</span>
                <ConcernBadge level={indicator.level} label={indicator.level_label} />
              </div>
              <div className="value">
                {indicator.key === 'land_tenure'
                  ? (LAND_TENURE_LABELS[cooperative.land_tenure ?? ''] ?? 'Okänt')
                  : formatValue(indicator.value, indicator.unit ?? '')}
              </div>
              <details>
                <summary>Varför?</summary>
                <p className="small">{indicator.rationale}</p>
                <p className="small muted">{indicator.rule}</p>
              </details>
            </div>
          ))}
        </div>
      </section>

      {overview.maintenance.length > 0 && <MaintenanceQuestions overview={overview} onChange={setOverview} />}

      {charts.length > 0 && (
        <section className="stack">
          <h2>Utveckling över tid</h2>
          <div className="chart-grid">
            {charts.map((series) => (
              <MetricChart key={series.key} series={series} />
            ))}
          </div>
        </section>
      )}

      <section className="card stack">
        <div className="spread">
          <h2>Nyckeltal och underlag</h2>
          <Completeness overview={overview} labels={metricLabels} onAdd={(metricKey) =>
            completeness.fiscal_year && setSelection({ metricKey, fiscalYear: completeness.fiscal_year })} />
        </div>
        <p className="small muted">
          Klicka på ett värde för att se källa, sida i dokumentet och beräkning, eller för att rätta det.{' '}
          <em>Kursiv</em> = beräknat av appen. <span style={{ color: 'var(--high)' }}>Rött</span> = motstridiga uppgifter.
          ✓ = kontrollerat, ✎ = manuellt angivet.
        </p>
        {tableYears.length === 0 ? (
          <p className="muted">Inga värden ännu.</p>
        ) : (
          <div className="table-scroll">
            <table className="kpi-table">
              <thead>
                <tr>
                  <th>Räkenskapsår</th>
                  {tableYears.map((year) => (
                    <th key={year}>{year}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {TABLE_GROUPS.map((group) => {
                  const rows = overview.metrics.filter((m) => m.category === group.category)
                  if (rows.length === 0) return null
                  return [
                    <tr className="group" key={group.category}>
                      <td colSpan={tableYears.length + 1}>{group.title}</td>
                    </tr>,
                    ...rows.map((series) => (
                      <tr key={series.key}>
                        <td title={series.description}>{series.label}</td>
                        {tableYears.map((year) => (
                          <td key={year}>
                            <ValueCell
                              series={series}
                              value={findValue(series, year)}
                              onOpen={() => setSelection({ metricKey: series.key, fiscalYear: year })}
                            />
                          </td>
                        ))}
                      </tr>
                    )),
                  ]
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {overview.findings.length > 0 && <Findings overview={overview} />}

      <section className="card stack">
        <h2>Dokument</h2>
        <ul className="list">
          {overview.documents.map((document) => (
            <DocumentRow
              key={document.id}
              document={document}
              others={others}
              onChanged={load}
              onMoved={(cooperativeId) => navigate(`/foreningar/${cooperativeId}`)}
            />
          ))}
        </ul>
        <h3>Lägg till dokument</h3>
        <p className="small muted">
          Fler årsredovisningar ger längre historik. Dokument med samma organisationsnummer kopplas automatiskt hit.
        </p>
        <DocumentUploader
          onAdded={(document) =>
            document.cooperative_id && document.cooperative_id !== id
              ? navigate(`/foreningar/${document.cooperative_id}`)
              : load()
          }
        />
      </section>

      {selection && selectedMetric && (
        <ValueDetails
          key={`${selection.metricKey}-${selection.fiscalYear}`}
          cooperativeId={cooperative.id}
          metric={selectedMetric}
          yearValue={selectedValue}
          fiscalYear={selection.fiscalYear}
          metricLabels={metricLabels}
          onClose={() => setSelection(null)}
          onChange={setOverview}
        />
      )}
    </div>
  )
}

function findValue(series: MetricSeries, year: number): YearValue | null {
  return series.values.find((v) => v.fiscal_year === year) ?? null
}

/** The series from the overview, or an empty one built from the catalogue for metrics without data. */
function findSeries(overview: CooperativeOverview, definitions: MetricDefinition[], key: string): MetricSeries | null {
  const existing = overview.metrics.find((m) => m.key === key)
  if (existing) return existing
  const definition = definitions.find((d) => d.key === key)
  if (!definition) return null
  return { ...definition, category: definition.category as MetricSeries['category'], values: [] }
}

function ValueCell({ series, value, onOpen }: { series: MetricSeries; value: YearValue | null; onOpen: () => void }) {
  if (!value) {
    return <span className="missing">–</span>
  }
  const status = value.display_status
  const marker = status === 'verified' ? '✓' : status === 'user_entered' ? '✎' : status === 'conflicting' ? '!' : null
  return (
    <button
      className={`value-button ${status === 'calculated' ? 'calculated' : ''} ${status === 'conflicting' ? 'conflicting' : ''}`}
      onClick={onOpen}
      title="Visa källa och detaljer"
    >
      {value.display_value === null ? 'Motstridigt' : formatValue(value.display_value, series.unit)}
      {marker && <span className="marker">{marker}</span>}
    </button>
  )
}

function Completeness({
  overview,
  labels,
  onAdd,
}: {
  overview: CooperativeOverview
  labels: Record<string, string>
  onAdd: (metricKey: string) => void
}) {
  const { available, missing, fiscal_year } = overview.completeness
  const total = available.length + missing.length
  if (total === 0) return null
  return (
    <details>
      <summary>
        <span className="row" style={{ display: 'inline-flex' }}>
          Fullständighet {fiscal_year}: {available.length} av {total} viktiga uppgifter
          <span className="meter" aria-hidden>
            <span style={{ width: `${(available.length / total) * 100}%` }} />
          </span>
        </span>
      </summary>
      {missing.length > 0 ? (
        <ul className="small">
          {missing.map((key) => (
            <li key={key}>
              {labels[key] ?? key}{' '}
              <button className="link small" onClick={() => onAdd(key)}>
                Ange
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="small">Alla viktiga uppgifter finns.</p>
      )}
    </details>
  )
}

function CooperativeHeader({
  overview,
  onChange,
  onDelete,
}: {
  overview: CooperativeOverview
  onChange: (overview: CooperativeOverview) => void
  onDelete: () => void
}) {
  const { cooperative } = overview
  const [editing, setEditing] = useState(false)
  const [name, setName] = useState(cooperative.name)
  const [organisationNumber, setOrganisationNumber] = useState(cooperative.organisation_number ?? '')
  const [landTenure, setLandTenure] = useState(cooperative.land_tenure ?? '')
  const [error, setError] = useState<string | null>(null)

  async function save(event: FormEvent) {
    event.preventDefault()
    setError(null)
    try {
      const changes: Parameters<typeof api.updateCooperative>[1] = { name }
      if (organisationNumber && organisationNumber !== cooperative.organisation_number) {
        changes.organisation_number = organisationNumber
      }
      if (landTenure && landTenure !== cooperative.land_tenure) {
        changes.land_tenure = landTenure as 'owned' | 'leasehold'
      }
      onChange(await api.updateCooperative(cooperative.id, changes))
      setEditing(false)
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Kunde inte spara.')
    }
  }

  if (editing) {
    return (
      <form className="card stack" onSubmit={save}>
        <label className="stack" style={{ gap: '0.25rem' }}>
          Namn
          <input value={name} onChange={(event) => setName(event.target.value)} required />
        </label>
        <label className="stack" style={{ gap: '0.25rem' }}>
          Organisationsnummer
          <input
            value={organisationNumber}
            onChange={(event) => setOrganisationNumber(event.target.value)}
            placeholder="769600-1234"
            pattern="\d{6}-\d{4}"
          />
        </label>
        <label className="stack" style={{ gap: '0.25rem' }}>
          Mark
          <select value={landTenure} onChange={(event) => setLandTenure(event.target.value)}>
            <option value="">Okänt</option>
            <option value="owned">Äganderätt (egen mark)</option>
            <option value="leasehold">Tomträtt</option>
          </select>
        </label>
        {error && <div className="notice error">{error}</div>}
        <div className="row">
          <button type="submit" className="primary">
            Spara
          </button>
          <button type="button" onClick={() => setEditing(false)}>
            Avbryt
          </button>
        </div>
      </form>
    )
  }

  return (
    <div className="spread">
      <div>
        <h1>{cooperative.name}</h1>
        <div className="muted small">
          Org.nr {cooperative.organisation_number ?? 'saknas'} · Mark:{' '}
          {cooperative.land_tenure ? LAND_TENURE_LABELS[cooperative.land_tenure] : 'okänt'}
          {overview.latest_fiscal_year && ` · Senaste räkenskapsår ${overview.latest_fiscal_year}`}
        </div>
        {cooperative.land_tenure_source && (
          <div className="muted small">Källa för mark: {cooperative.land_tenure_source}</div>
        )}
      </div>
      <div className="row">
        <button onClick={() => setEditing(true)}>Redigera</button>
        <button className="danger" onClick={onDelete}>
          Ta bort
        </button>
      </div>
    </div>
  )
}

function Findings({ overview }: { overview: CooperativeOverview }) {
  const topics = [...new Set(overview.findings.map((f) => f.topic))]
  return (
    <section className="card stack">
      <h2>Underhåll, renoveringar och lån – i dokumenten</h2>
      <p className="small muted">
        Ordagranna utdrag där dokumenten nämner ämnet. De är inte tolkade: att något nämns betyder inte att det är gjort
        eller planerat, och att något saknas här betyder inte att det inte har gjorts.
      </p>
      {topics.map((topic) => (
        <details key={topic}>
          <summary>
            {topic} ({overview.findings.filter((f) => f.topic === topic).length})
          </summary>
          <ul className="list small">
            {overview.findings
              .filter((f) => f.topic === topic)
              .map((finding, index) => (
                <li key={index}>
                  ”{finding.excerpt}”{' '}
                  <DocumentLink documentId={finding.document_id} page={finding.page}>
                    s. {finding.page}
                  </DocumentLink>
                </li>
              ))}
          </ul>
        </details>
      ))}
    </section>
  )
}

function DocumentRow({
  document,
  others,
  onChanged,
  onMoved,
}: {
  document: DocumentSummary
  others: CooperativeListItem[]
  onChanged: () => void
  onMoved: (cooperativeId: number) => void
}) {
  const [error, setError] = useState<string | null>(null)

  async function move(cooperativeId: number) {
    const target = others.find((c) => c.id === cooperativeId)
    if (!target || !confirm(`Flytta dokumentet och dess värden till ${target.name}?`)) return
    try {
      await api.moveDocument(document.id, cooperativeId)
      onMoved(cooperativeId)
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Kunde inte flytta dokumentet.')
    }
  }

  async function remove() {
    if (!confirm(`Ta bort ${document.original_filename} och alla värden från det?`)) return
    await api.deleteDocument(document.id)
    onChanged()
  }

  const statusClass = document.extraction_status === 'succeeded' ? 'low' : document.extraction_status === 'partial' ? 'moderate' : 'high'
  return (
    <li className="stack" style={{ gap: '0.35rem' }}>
      <div className="spread">
        <DocumentLink documentId={document.id}>{document.original_filename}</DocumentLink>
        <span className={`badge ${statusClass}`}>{EXTRACTION_STATUS_LABELS[document.extraction_status]}</span>
      </div>
      <div className="small muted">
        {DOCUMENT_TYPE_LABELS[document.document_type] ?? document.document_type}
        {document.reporting_year && ` · räkenskapsår ${document.reporting_year}`}
        {document.fiscal_period_start && document.fiscal_period_end &&
          ` (${document.fiscal_period_start} – ${document.fiscal_period_end})`}
        {` · ${document.page_count} sidor · tillagd ${formatDate(document.uploaded_at)}`}
        {document.document_url && (
          <>
            {' · '}
            <a href={document.document_url} target="_blank" rel="noreferrer">
              ursprunglig länk
            </a>
          </>
        )}
      </div>
      <div className="row small">
        {others.length > 0 && (
          <select
            value=""
            onChange={(event) => move(Number(event.target.value))}
            aria-label="Flytta till annan förening"
          >
            <option value="">Fel förening? Flytta till …</option>
            {others.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        )}
        <button className="link danger" onClick={remove}>
          Ta bort dokument
        </button>
      </div>
      {error && <div className="notice error">{error}</div>}
    </li>
  )
}
