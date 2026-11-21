import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, ApiError, type ComparisonCell, type ComparisonRow, type CooperativeComparison } from '../api'
import { ScoreBadge } from '../components/Badges'
import { ComparisonChart, SERIES_COLORS } from '../components/ComparisonChart'
import { formatValue, LAND_TENURE_LABELS, STATUS_LABELS } from '../format'

const AREA_BASIS_LABELS: Record<string, string> = {
  total_area: 'per m² totalyta',
  tenant_owned_area: 'per m² bostadsrättsyta',
}

export function ComparisonPage() {
  const [searchParams] = useSearchParams()
  const idKey = searchParams.get('ids') ?? ''
  // Each result remembers which selection it belongs to, so a slow earlier answer is never shown for a newer URL.
  const [result, setResult] = useState<{ key: string; comparison?: CooperativeComparison; error?: string } | null>(
    null,
  )
  const [showAll, setShowAll] = useState(false)

  useEffect(() => {
    let current = true
    api
      .compareCooperatives(idKey)
      .then((comparison) => current && setResult({ key: idKey, comparison }))
      .catch(
        (caught) =>
          current &&
          setResult({ key: idKey, error: caught instanceof ApiError ? caught.message : 'Kunde inte jämföra föreningarna.' }),
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
        <Link to="/">Välj föreningar på översikten</Link>
      </div>
    )
  }
  if (!comparison) return <p className="muted">Laddar …</p>

  const { cooperatives, warnings } = comparison
  const rows = showAll ? comparison.rows : comparison.rows.filter((row) => row.is_default)
  const hiddenCount = comparison.rows.length - comparison.rows.filter((row) => row.is_default).length
  const charts = comparison.rows.filter(
    (row) => row.is_default && row.cells.filter((cell) => cell.value !== null).length >= 2,
  )

  return (
    <div className="stack" style={{ gap: '1.5rem' }}>
      <div className="small">
        <Link to="/">← Översikt</Link>
      </div>
      <div>
        <h1>Jämför föreningar</h1>
        <p className="muted">
          Varje förening jämförs på sitt senaste räkenskapsår. Färgerna visar riskbedömningen för respektive nyckeltal,
          inte en rangordning.
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
          <table className="kpi-table comparison-table">
            <thead>
              <tr>
                <th>Förening</th>
                {cooperatives.map((cooperative, index) => (
                  <th key={cooperative.id}>
                    <div className="stack" style={{ gap: '0.3rem', alignItems: 'flex-end' }}>
                      <span className="row" style={{ justifyContent: 'flex-end' }}>
                        <span className="swatch" style={{ background: SERIES_COLORS[index] }} aria-hidden />
                        <Link to={`/foreningar/${cooperative.id}`} className="cooperative-name">
                          {cooperative.name}
                        </Link>
                      </span>
                      <span>
                        Räkenskapsår {cooperative.fiscal_year ?? 'okänt'}
                        {cooperative.period_months && cooperative.period_months !== 12 && (
                          <span className="marker" title={`${cooperative.period_months} månader`}>
                            ⚠
                          </span>
                        )}
                      </span>
                      <Link to={`/foreningar/${cooperative.id}`} title="Så räknas poängen">
                        <ScoreBadge score={cooperative.score} label={cooperative.score_label} prefix="Poäng: " />
                      </Link>
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>Mark</td>
                {cooperatives.map((cooperative) => (
                  <td key={cooperative.id}>
                    {cooperative.land_tenure ? LAND_TENURE_LABELS[cooperative.land_tenure] : <span className="missing">Okänt</span>}
                  </td>
                ))}
              </tr>
              <tr>
                <td>Fullständighet</td>
                {cooperatives.map((cooperative) => (
                  <td key={cooperative.id}>
                    {cooperative.completeness_available} av {cooperative.completeness_total} uppgifter
                  </td>
                ))}
              </tr>
              {rows.map((row) => (
                <tr key={row.key}>
                  <td>
                    <span title={row.description}>{row.label}</span>
                    {row.area_basis && (
                      <div className="small muted" title={row.note ?? undefined}>
                        {AREA_BASIS_LABELS[row.area_basis] ?? row.area_basis} ⓘ
                      </div>
                    )}
                  </td>
                  {row.cells.map((cell) => (
                    <td key={cell.cooperative_id} className={cell.level ? `level-cell ${cell.level}` : undefined}>
                      <ComparisonValue row={row} cell={cell} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {hiddenCount > 0 && (
          <div>
            <button className="link" onClick={() => setShowAll(!showAll)}>
              {showAll ? 'Visa färre nyckeltal' : `Visa alla nyckeltal (${hiddenCount} till)`}
            </button>
          </div>
        )}
        <p className="small muted">
          <em>Kursiv</em> = beräknat av appen. ! = motstridiga uppgifter. ⚠ = se varning. Klicka på en förening för källor
          och detaljer.
        </p>
      </section>

      {charts.length > 0 && (
        <section className="stack">
          <h2>Diagram</h2>
          <div className="chart-grid">
            {charts.map((row) => (
              <ComparisonChart key={row.key} row={row} cooperatives={cooperatives} />
            ))}
          </div>
        </section>
      )}
    </div>
  )
}

function ComparisonValue({ row, cell }: { row: ComparisonRow; cell: ComparisonCell }) {
  if (cell.value === null) {
    return (
      <span
        className={cell.status === 'conflicting' ? 'conflicting-text' : 'missing'}
        title={cell.missing_reason ?? undefined}
      >
        {cell.status === 'conflicting' ? 'Motstridigt' : 'Saknas'}
      </span>
    )
  }
  const title = [STATUS_LABELS[cell.status], cell.level_label, cell.warning].filter(Boolean).join(' · ')
  return (
    <span title={title} className={cell.status === 'calculated' ? 'calculated-text' : cell.status === 'conflicting' ? 'conflicting-text' : ''}>
      {formatValue(cell.value, row.unit)}
      {cell.status === 'conflicting' && <span className="marker">!</span>}
      {cell.warning && cell.status !== 'conflicting' && <span className="marker">⚠</span>}
    </span>
  )
}
