import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, ApiError, type CooperativeListItem, type DocumentSummary } from '../api'
import { ConcernBadge } from '../components/Badges'
import { DocumentUploader } from '../components/DocumentUploader'
import { formatDate } from '../format'

export function Dashboard() {
  const navigate = useNavigate()
  const [cooperatives, setCooperatives] = useState<CooperativeListItem[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .listCooperatives()
      .then(setCooperatives)
      .catch((caught) => setError(caught instanceof ApiError ? caught.message : 'Kunde inte hämta föreningar.'))
  }, [])

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
        <h2>Föreningar</h2>
        {error && <div className="notice error">{error}</div>}
        {cooperatives === null && !error && <p className="muted">Laddar …</p>}
        {cooperatives?.length === 0 && <p className="muted">Inga föreningar ännu. Ladda upp en årsredovisning ovan.</p>}
        {cooperatives && cooperatives.length > 0 && (
          <ul className="list card" style={{ padding: '0 1.25rem' }}>
            {cooperatives.map((cooperative) => (
              <li key={cooperative.id} className="spread">
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
                <ConcernBadge level={cooperative.overall_level} label={cooperative.overall_label} />
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
