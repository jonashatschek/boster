import { useEffect, useRef, useState, type FormEvent } from 'react'
import { api, ApiError, type CooperativeOverview, type MetricSeries, type YearValue } from '../api'
import { formatExact, formatValue, METHOD_LABELS } from '../format'
import { StatusBadge } from './Badges'
import { DocumentLink } from './DocumentLink'

interface Props {
  cooperativeId: number
  metric: MetricSeries
  yearValue: YearValue | null // null when adding a value for a year without data.
  fiscalYear: number
  metricLabels: Record<string, string>
  onClose: () => void
  onChange: (overview: CooperativeOverview) => void
}

/** Everything known about one value: sources, calculation, conflicts, and manual correction. */
export function ValueDetails({ cooperativeId, metric, yearValue, fiscalYear, metricLabels, onClose, onChange }: Props) {
  const dialog = useRef<HTMLDialogElement>(null)
  const [manualValue, setManualValue] = useState('')
  const [manualNote, setManualNote] = useState('')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    dialog.current?.showModal()
  }, [])

  /** Returns true when the change was saved. */
  async function act(action: () => Promise<CooperativeOverview>): Promise<boolean> {
    setError(null)
    try {
      onChange(await action())
      return true
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Något gick fel.')
      return false
    }
  }

  function submitManual(event: FormEvent) {
    event.preventDefault()
    const value = Number(manualValue.replace(/\s/g, '').replace(',', '.'))
    if (!Number.isFinite(value)) {
      setError('Ange ett tal, t.ex. 3613 eller 4,5.')
      return
    }
    act(() =>
      api.addObservation(cooperativeId, { metric_key: metric.key, fiscal_year: fiscalYear, value, note: manualNote || undefined }),
    ).then((saved) => {
      if (!saved) return
      setManualValue('')
      setManualNote('')
    })
  }

  const reported = yearValue?.reported
  const calculated = yearValue?.calculated
  const inputLabel = (key: string) => {
    const previous = key.startsWith('previous:')
    const label = metricLabels[key.replace('previous:', '')] ?? key
    return previous ? `${label} (föregående år)` : label
  }

  return (
    <dialog ref={dialog} onClose={onClose} aria-labelledby="value-details-title">
      <div className="stack">
        <div className="spread">
          <h2 id="value-details-title">
            {metric.label}, {fiscalYear}
          </h2>
          <button onClick={() => dialog.current?.close()} aria-label="Stäng">
            Stäng
          </button>
        </div>
        <p className="muted small">{metric.description}</p>

        {yearValue && (
          <div className="row">
            <strong style={{ fontSize: '1.3rem' }}>{formatValue(yearValue.display_value, metric.unit)}</strong>
            <StatusBadge status={yearValue.display_status} />
          </div>
        )}
        {yearValue?.warning && <div className="notice warning">{yearValue.warning}</div>}

        {reported && (
          <section className="stack">
            <h3>Källor</h3>
            {reported.sources.map((source) => (
              <div className="source stack" key={source.observation_id} style={{ gap: '0.3rem' }}>
                <div className="spread">
                  <strong>{formatExact(source.value, metric.unit)}</strong>
                  <StatusBadge status={source.status} />
                </div>
                <div className="small">
                  {METHOD_LABELS[source.method] ?? source.method}
                  {source.document_id && (
                    <>
                      {' · '}
                      <DocumentLink documentId={source.document_id} page={source.page}>
                        {source.document_name}
                        {source.page ? `, sida ${source.page}` : ''}
                      </DocumentLink>
                    </>
                  )}
                </div>
                {source.printed_label && <div className="small muted">Rad i dokumentet: ”{source.printed_label}”</div>}
                {source.note && <div className="small muted">{source.note}</div>}
                <div className="row small">
                  {source.status === 'extracted' && (
                    <button className="link" onClick={() => act(() => api.verifyObservation(source.observation_id))}>
                      Markera som kontrollerad
                    </button>
                  )}
                  {source.method === 'manual' && (
                    <button className="link danger" onClick={() => act(() => api.deleteObservation(source.observation_id))}>
                      Ta bort manuellt värde
                    </button>
                  )}
                </div>
              </div>
            ))}
          </section>
        )}

        {calculated && (
          <section className="stack">
            <h3>Egen beräkning</h3>
            <div className="small">
              <code>{calculated.formula}</code>
            </div>
            {calculated.value !== null && (
              <div>
                Resultat: <strong>{formatExact(Math.round(calculated.value * 100) / 100, metric.unit)}</strong>
              </div>
            )}
            {Object.keys(calculated.inputs).length > 0 && (
              <dl className="facts small">
                {Object.entries(calculated.inputs).map(([key, value]) => (
                  <div key={key} style={{ display: 'contents' }}>
                    <dt>{inputLabel(key)}</dt>
                    <dd>{formatExact(value, '')}</dd>
                  </div>
                ))}
              </dl>
            )}
            {calculated.missing_inputs.length > 0 && (
              <div className="notice small">
                Kan inte beräknas. Saknas: {calculated.missing_inputs.map(inputLabel).join(', ')}.
              </div>
            )}
            {calculated.note && <div className="notice small">{calculated.note}</div>}
          </section>
        )}

        <section className="stack">
          <h3>{yearValue ? 'Rätta eller komplettera' : 'Ange värde'}</h3>
          <p className="small muted">
            Ett manuellt värde ersätter värden från dokumenten i analysen. Ursprungliga värden sparas och visas fortfarande som källor.
          </p>
          <form className="stack" onSubmit={submitManual}>
            <div className="input-row">
              <input
                inputMode="decimal"
                placeholder={`Värde i ${metric.unit}`}
                value={manualValue}
                onChange={(event) => setManualValue(event.target.value)}
                aria-label="Värde"
              />
              <button type="submit" className="primary" disabled={!manualValue.trim()}>
                Spara
              </button>
            </div>
            <input
              placeholder="Kommentar, t.ex. var värdet kommer ifrån (valfritt)"
              value={manualNote}
              onChange={(event) => setManualNote(event.target.value)}
              aria-label="Kommentar"
            />
          </form>
        </section>
        {error && <div className="notice error">{error}</div>}
      </div>
    </dialog>
  )
}
