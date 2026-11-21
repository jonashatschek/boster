import type { CooperativeScore, ScorePart, SourceRef } from '../api'
import { formatValue } from '../format'
import { StatusBadge } from './Badges'

const oneDecimal = new Intl.NumberFormat('sv-SE', { maximumFractionDigits: 1 })
const integer = new Intl.NumberFormat('sv-SE', { maximumFractionDigits: 0 })
const percent = new Intl.NumberFormat('sv-SE', { style: 'percent', maximumFractionDigits: 0 })

/**
 * The cooperative's 0–100 score. The summary (score, coverage, missing parts) is always visible; the table
 * of parts opens on click. Neutral styling: the score summarises rules of thumb and is not a credit rating.
 */
export function ScoreCard({ score, disclaimer }: { score: CooperativeScore; disclaimer: string }) {
  const total = score.parts.reduce((sum, part) => sum + contribution(part), 0)
  // Below the minimum coverage there is no score, so nothing that adds up to one is shown.
  const scored = score.score !== null
  return (
    <div className="score-card stack">
      <div className="score-summary">
        <span className="small muted">Poäng</span>
        {score.score !== null ? (
          <strong className="score-value">
            {score.score} <span className="muted">/ 100</span>
          </strong>
        ) : (
          <strong className="score-value insufficient">{score.label}</strong>
        )}
      </div>
      <p className="small">{score.coverage}</p>
      {score.missing.length > 0 && (
        <div className="small">
          <span className="muted">Saknas: </span>
          {score.missing.map((part, index) => (
            <span key={part.key}>
              {index > 0 && ', '}
              {part.label} <span className="muted">({part.reason.replace(/\.$/, '').toLowerCase()})</span>
            </span>
          ))}
        </div>
      )}
      <p className="small muted">{disclaimer}</p>
      {score.parts.length > 0 && (
        <details>
          <summary>Så räknas poängen</summary>
          <div className="table-scroll">
            <table className="score-table small">
              <thead>
                <tr>
                  <th>Nyckeltal</th>
                  <th>Värde</th>
                  <th>Källa</th>
                  <th>Skala</th>
                  <th className="num">Poäng</th>
                  <th className="num">Vikt</th>
                  {scored && <th className="num">Bidrag</th>}
                </tr>
              </thead>
              <tbody>
                {score.parts.map((part) => (
                  <tr key={part.key}>
                    <td>{part.label}</td>
                    <td>
                      {part.value_text ?? formatValue(part.value, part.unit ?? '')}
                      {part.fiscal_year !== null && part.inputs.length === 0 && (
                        <span className="muted"> ({part.fiscal_year})</span>
                      )}
                      {part.inputs.length > 0 && (
                        <div className="muted">
                          {part.inputs.map((input) => integer.format(input.value)).join(' → ')} (
                          {part.inputs[0].fiscal_year}–{part.inputs[part.inputs.length - 1].fiscal_year})
                        </div>
                      )}
                      <div>
                        <StatusBadge status={part.status} />
                      </div>
                    </td>
                    <td>
                      <Source part={part} />
                    </td>
                    <td className="muted">{part.rule}</td>
                    <td className="num">{oneDecimal.format(part.part_score)}</td>
                    <td className="num" title={part.weight_reason}>
                      {part.weight}
                      {scored && <span className="muted"> ({percent.format(part.effective_weight)})</span>}
                    </td>
                    {scored && <td className="num">{oneDecimal.format(contribution(part))}</td>}
                  </tr>
                ))}
              </tbody>
              <tfoot>
                {scored ? (
                  <tr>
                    <td colSpan={6}>Summa, avrundad till hela poäng</td>
                    <td className="num">
                      <strong>
                        {oneDecimal.format(total)} → {score.score}
                      </strong>
                    </td>
                  </tr>
                ) : (
                  <tr>
                    <td colSpan={6}>Ingen poäng beräknas: för få nyckeltal finns (se ovan).</td>
                  </tr>
                )}
              </tfoot>
            </table>
          </div>
          <p className="small">{score.rule}</p>
          <p className="small muted">
            {scored &&
              'Bidrag = poäng × delens andel av vikten. Bidragen är avrundade var för sig; summan räknas på de exakta värdena. '}
            Vikternas motiveringar visas när du håller muspekaren över vikten.
            Vikter och gränser står i backend/config/risk_rules.toml i källkoden.
          </p>
        </details>
      )}
    </div>
  )
}

/** Each part's points weighted by its share of the weight; the contributions add up to the score. */
function contribution(part: ScorePart): number {
  return part.part_score * part.effective_weight
}

function Source({ part }: { part: ScorePart }) {
  if (part.source_text) return <span>{part.source_text}</span>
  if (part.inputs.length > 0) {
    // A trend: one line per year, so each value can be traced to where it came from.
    return (
      <>
        {part.inputs.map((input) => (
          <div key={input.fiscal_year}>
            <span className="muted">{input.fiscal_year}: </span>
            <SourceList sources={input.sources} formula={input.formula} />
          </div>
        ))}
      </>
    )
  }
  return <SourceList sources={part.sources} formula={part.formula} />
}

function SourceList({ sources, formula }: { sources: SourceRef[]; formula: string | null }) {
  if (formula) return <span className="muted">Beräknat: {formula}</span>
  if (sources.length === 0) return <span className="muted">–</span>
  return (
    <>
      {sources.map((source, index) => (
        <span key={source.observation_id}>
          {index > 0 && '; '}
          {source.document_name ?? (source.status === 'user_entered' ? 'Angivet av dig' : 'Okänd källa')}
          {source.page && `, s. ${source.page}`}
          {source.printed_label && `: ”${source.printed_label}”`}
        </span>
      ))}
    </>
  )
}
