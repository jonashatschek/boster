import { Fragment, useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import {
  api,
  ApiError,
  type ComparedProperty,
  type Finding,
  type PropertyComparison,
  type PropertyComparisonCell,
  type PropertyComparisonRow,
  type VerificationStatus,
} from '../api'
import { ConcernBadge, StatusBadge } from '../components/Badges'
import { DocumentLink } from '../components/DocumentLink'
import { formatDate, formatValue } from '../format'

// Listing values are read from the listing, not from a document.
const LISTING_LABELS: Partial<Record<VerificationStatus, string>> = { extracted: 'Från annonsen' }
const LINK_LABELS: Partial<Record<VerificationStatus, string>> = {
  extracted: 'Kopplad på namn',
  user_entered: 'Kopplad manuellt',
}
// Nearest stops come from Trafiklab and OpenStreetMap, not from the listing.
const TRANSPORT_LABELS: Partial<Record<VerificationStatus, string>> = { extracted: 'Från Trafiklab/OpenStreetMap' }
const COOPERATIVE_UNITS = new Set(['kr/kvm', '%', 'ggr', 'kvm'])

export function PropertyComparisonPage() {
  const [searchParams] = useSearchParams()
  const idKey = searchParams.get('ids') ?? ''
  // Each result remembers which selection it belongs to, so a slow earlier answer is never shown for a newer URL.
  const [result, setResult] = useState<{ key: string; comparison?: PropertyComparison; error?: string } | null>(null)

  useEffect(() => {
    let current = true
    api
      .compareProperties(idKey)
      .then((comparison) => current && setResult({ key: idKey, comparison }))
      .catch(
        (caught) =>
          current &&
          setResult({ key: idKey, error: caught instanceof ApiError ? caught.message : 'Kunde inte jämföra bostäderna.' }),
      )
    return () => {
      current = false
    }
  }, [idKey])

  const comparison = result?.key === idKey ? result.comparison : undefined
  const error = result?.key === idKey ? result.error : undefined

  if (error) {
    return (
      <div className="stack">
        <div className="notice error">{error}</div>
        <Link to="/">Välj bostäder på översikten</Link>
      </div>
    )
  }
  if (!comparison) return <p className="muted">Laddar …</p>

  const { properties, rows, warnings } = comparison
  const groups = [...new Set(rows.map((row) => row.group))]
  const columns = properties.length + 1

  return (
    <div className="stack" style={{ gap: '1.5rem' }}>
      <div className="small">
        <Link to="/">← Översikt</Link>
      </div>
      <div>
        <h1>Jämför bostäder</h1>
        <p className="muted">
          Bostäderna visas sida vid sida utan rangordning. Varje värde visar varifrån det kommer. Färgerna på föreningens
          nyckeltal visar riskbedömningen, inte vilken bostad som är bäst.
        </p>
      </div>

      {warnings.length > 0 && (
        <div className="stack">
          {warnings.map((warning) => (
            <div className="notice warning" key={warning}>
              {warning}
            </div>
          ))}
        </div>
      )}

      <section className="card stack">
        <div className="table-scroll">
          <table className="kpi-table comparison-table property-comparison">
            <thead>
              <tr>
                <th>Bostad</th>
                {properties.map((property) => (
                  <th key={property.id}>
                    <Link to={`/bostader/${property.id}`}>{propertyName(property)}</Link>
                    {property.source_name && <div className="small muted">{property.source_name}</div>}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {groups.map((group) => (
                <Fragment key={group}>
                  <tr className="group-row">
                    <th colSpan={columns}>{group}</th>
                  </tr>
                  {rows
                    .filter((row) => row.group === group)
                    .map((row) => (
                      <tr key={row.key}>
                        <td>
                          <span title={row.note ?? undefined}>{row.label}</span>
                          {row.is_estimate && (
                            <div>
                              <span className="badge status-estimated" title={row.note ?? undefined}>
                                Uppskattning
                              </span>
                            </div>
                          )}
                        </td>
                        {row.cells.map((cell, index) => (
                          <td key={cell.property_id} className={cell.level ? `level-cell ${cell.level}` : undefined}>
                            {row.kind === 'findings' && cell.value !== null ? (
                              <MaintenanceTopics findings={properties[index].maintenance} />
                            ) : (
                              <CellValue row={row} cell={cell} />
                            )}
                          </td>
                        ))}
                      </tr>
                    ))}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
        <p className="small muted">
          Håll muspekaren över ett värde för källan. <em>Kursiv</em> = beräknat av appen. Rader märkta Uppskattning bygger
          på antaganden, inte på kontrollerade uppgifter. Klicka på en bostad för alla detaljer.
        </p>
      </section>
    </div>
  )
}

function propertyName(property: ComparedProperty): string {
  return property.address ?? property.title ?? `Bostad ${property.id}`
}

function CellValue({ row, cell }: { row: PropertyComparisonRow; cell: PropertyComparisonCell }) {
  const title = [cell.excerpt, cell.note, cell.fiscal_year ? `Räkenskapsår ${cell.fiscal_year}` : null]
    .filter(Boolean)
    .join('\n')
  if (cell.value === null) {
    return (
      <span title={title || undefined}>
        <span className={cell.status === 'conflicting' ? 'conflicting-text' : 'missing'}>
          {cell.status === 'conflicting' ? 'Motstridigt' : 'Saknas'}
        </span>
        {cell.note && <div className="small muted">{cell.note}</div>}
      </span>
    )
  }
  if (row.kind === 'level' && cell.level) {
    return (
      <span title={title || undefined}>
        <ConcernBadge level={cell.level} label={cell.level_label ?? String(cell.value)} />
        {cell.fiscal_year && <div className="small muted">Räkenskapsår {cell.fiscal_year}</div>}
      </span>
    )
  }
  const labels = row.key === 'cooperative'
    ? LINK_LABELS
    : row.key.startsWith('transport:')
      ? TRANSPORT_LABELS
      : row.key.startsWith('risk:')
        ? undefined
        : LISTING_LABELS
  return (
    <span title={title || undefined}>
      <span className={cell.status === 'calculated' ? 'calculated-text' : undefined}>{formatCell(row, cell)}</span>
      {row.key.startsWith('risk:') && cell.level_label && <div className="small">{cell.level_label}</div>}
      <div>
        <StatusBadge status={cell.status} labels={labels} />
      </div>
    </span>
  )
}

function formatCell(row: PropertyComparisonRow, cell: PropertyComparisonCell): string {
  const value = cell.value
  if (typeof value === 'boolean') return value ? 'Ja' : 'Nej'
  if (typeof value !== 'number') return row.kind === 'date' ? formatDate(String(value)) : String(value)
  if (!row.unit) return String(value)
  if (COOPERATIVE_UNITS.has(row.unit)) return formatValue(value, row.unit)
  const digits = row.unit === 'm²' || row.unit === 'rum' ? 1 : 0
  return `${new Intl.NumberFormat('sv-SE', { maximumFractionDigits: digits }).format(value)} ${row.unit}`
}

function MaintenanceTopics({ findings: all }: { findings: Finding[] }) {
  const byTopic = new Map<string, Finding[]>()
  for (const finding of all) {
    byTopic.set(finding.topic, [...(byTopic.get(finding.topic) ?? []), finding])
  }
  return (
    <div className="stack" style={{ gap: '0.25rem', textAlign: 'left' }}>
      {[...byTopic].map(([topic, findings]) => (
        <details key={topic}>
          <summary>
            {topic} <span className="muted small">(s. {[...new Set(findings.map((f) => f.page))].join(', ')})</span>
          </summary>
          <ul className="small" style={{ paddingLeft: '1rem' }}>
            {findings.map((finding, index) => (
              <li key={index}>
                ”{finding.excerpt}”{' '}
                <DocumentLink documentId={finding.document_id} page={finding.page}>
                  {finding.document_name}, s. {finding.page}
                </DocumentLink>
              </li>
            ))}
          </ul>
        </details>
      ))}
    </div>
  )
}
