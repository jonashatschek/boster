import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, ApiError, MAX_COMPARED_COOPERATIVES, type CooperativeListItem, type DocumentSummary } from '../api'
import { ConcernBadge } from '../components/Badges'
import { DocumentUploader } from '../components/DocumentUploader'
import { formatDate } from '../format'

export function Dashboard() {
  const navigate = useNavigate()
  const [cooperatives, setCooperatives] = useState<CooperativeListItem[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<number[]>([])

  useEffect(() => {
    api
      .listCooperatives()
      .then(setCooperatives)
      .catch((caught) => setError(caught instanceof ApiError ? caught.message : 'Kunde inte hämta föreningar.'))
  }, [])

  function toggleSelected(id: number) {
    setSelected((current) =>
      current.includes(id)
        ? current.filter((selectedId) => selectedId !== id)
        : current.length < MAX_COMPARED_COOPERATIVES
          ? [...current, id]
          : current,
    )
  }

  function onDocumentAdded(document: DocumentSummary) {
    if (document.cooperative_id) navigate(`/foreningar/${document.cooperative_id}`)
    else setError(`${document.original_filename}: ${document.extraction_messages.join(' ')}`)
  }

  return (
    <div className="stack" style={{ gap: '1.5rem' }}>
      <div>
        <h1>Översikt</h1>
        <p className="muted">Ladda upp en förenings årsredovisning för att se nyckeltal, risker och källor.</p>
      </div>

      <div className="grid-2">
        <section className="card stack">
          <h2>Analysera en förening</h2>
          <DocumentUploader onAdded={onDocumentAdded} />
        </section>
        <section className="card stack">
          <h2>Analysera en bostad</h2>
          <div className="input-row">
            <input type="url" placeholder="Länk till annons på Hemnet, Booli eller mäklarsida" disabled aria-label="Annonslänk" />
            <button disabled>Analysera</button>
          </div>
          <p className="small muted">
            Kommer i nästa steg. Då kan du klistra in en annonslänk, eller annonsens text om sidan inte går att hämta, och
            koppla bostaden till en förening.
          </p>
        </section>
      </div>

      <section>
        <div className="spread">
          <h2>Föreningar</h2>
          {cooperatives && cooperatives.length >= 2 && (
            <span className="small muted">Bocka i 2–{MAX_COMPARED_COOPERATIVES} föreningar för att jämföra dem</span>
          )}
        </div>
        {error && <div className="notice error">{error}</div>}
        {cooperatives === null && !error && <p className="muted">Laddar …</p>}
        {cooperatives?.length === 0 && <p className="muted">Inga föreningar ännu. Ladda upp en årsredovisning ovan.</p>}
        {cooperatives && cooperatives.length > 0 && (
          <ul className="list card" style={{ padding: '0 1.25rem' }}>
            {cooperatives.map((cooperative) => (
              <li key={cooperative.id} className="spread">
                <label className="select-item">
                  <input
                    type="checkbox"
                    checked={selected.includes(cooperative.id)}
                    disabled={!selected.includes(cooperative.id) && selected.length >= MAX_COMPARED_COOPERATIVES}
                    onChange={() => toggleSelected(cooperative.id)}
                    aria-label={`Välj ${cooperative.name} för jämförelse`}
                  />
                  <div>
                    <Link to={`/foreningar/${cooperative.id}`}>
                      <strong>{cooperative.name}</strong>
                    </Link>
                    <div className="small muted">
                      {cooperative.organisation_number ?? 'Org.nr saknas'} · {cooperative.document_count} dokument
                      {cooperative.latest_fiscal_year && ` · senaste år ${cooperative.latest_fiscal_year}`} · uppdaterad{' '}
                      {formatDate(cooperative.updated_at)}
                    </div>
                  </div>
                </label>
                <ConcernBadge level={cooperative.overall_level} label={cooperative.overall_label} />
              </li>
            ))}
          </ul>
        )}
        {selected.length > 0 && (
          <div className="compare-bar">
            <span>
              {selected.length} {selected.length === 1 ? 'förening vald' : 'föreningar valda'}
              {selected.length === 1 && <span className="muted"> – välj minst en till</span>}
              {selected.length === MAX_COMPARED_COOPERATIVES && <span className="muted"> (max)</span>}
            </span>
            <span className="row">
              <button onClick={() => setSelected([])}>Rensa</button>
              <button className="primary" disabled={selected.length < 2} onClick={() => navigate(`/jamfor?ids=${selected.join(',')}`)}>
                Jämför
              </button>
            </span>
          </div>
        )}
      </section>
    </div>
  )
}
