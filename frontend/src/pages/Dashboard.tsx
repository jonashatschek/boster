import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  api,
  ApiError,
  MAX_COMPARED_COOPERATIVES,
  MAX_COMPARED_PROPERTIES,
  type CooperativeListItem,
  type DocumentSummary,
  type PropertyListItem,
} from '../api'
import { ScoreBadge } from '../components/Badges'
import { CompareBar } from '../components/CompareBar'
import { DocumentUploader } from '../components/DocumentUploader'
import { ListingImporter } from '../components/ListingImporter'
import { formatDate } from '../format'
import { toggleId } from '../selection'

export function Dashboard() {
  const navigate = useNavigate()
  const [cooperatives, setCooperatives] = useState<CooperativeListItem[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<number[]>([])
  const [properties, setProperties] = useState<PropertyListItem[] | null>(null)
  const [selectedProperties, setSelectedProperties] = useState<number[]>([])
  const [propertyError, setPropertyError] = useState<string | null>(null)

  function loadCooperatives() {
    api
      .listCooperatives()
      .then(setCooperatives)
      .catch((caught) => setError(caught instanceof ApiError ? caught.message : 'Kunde inte hämta föreningar.'))
  }

  function loadProperties() {
    api
      .listProperties()
      .then(setProperties)
      .catch(() => setProperties([]))
  }

  useEffect(() => {
    loadCooperatives()
    loadProperties()
  }, [])

  function propertyName(property: PropertyListItem) {
    return property.address ?? property.title ?? 'bostaden'
  }

  async function deleteProperty(property: PropertyListItem) {
    if (!confirm(`Ta bort ${propertyName(property)}? Det går inte att ångra.`)) return
    try {
      await api.deleteProperty(property.id)
      setPropertyError(null)
      setSelectedProperties((current) => current.filter((id) => id !== property.id))
      loadProperties()
    } catch (caught) {
      setPropertyError(caught instanceof ApiError ? caught.message : 'Kunde inte ta bort bostaden.')
    }
  }

  async function deleteAllProperties(count: number) {
    const what = count === 1 ? '1 bostad' : `alla ${count} bostäder`
    if (!confirm(`Ta bort ${what}? Det går inte att ångra. Exportera först om du vill spara en kopia.`)) return
    try {
      await api.deleteAllProperties()
      setPropertyError(null)
      setSelectedProperties([])
      loadProperties()
    } catch (caught) {
      setPropertyError(caught instanceof ApiError ? caught.message : 'Kunde inte ta bort bostäderna.')
    }
  }

  async function deleteCooperative(cooperative: CooperativeListItem) {
    if (!confirm(`Ta bort ${cooperative.name} med alla dokument och värden? Det går inte att ångra.`)) return
    try {
      await api.deleteCooperative(cooperative.id)
      setError(null)
      setSelected((current) => current.filter((id) => id !== cooperative.id))
      loadCooperatives()
      loadProperties() // Apartments linked to it are now unlinked.
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Kunde inte ta bort föreningen.')
    }
  }

  async function deleteAllCooperatives(count: number) {
    const what = count === 1 ? '1 förening' : `alla ${count} föreningar`
    if (!confirm(`Ta bort ${what} med alla dokument och värden? Det går inte att ångra. Exportera först om du vill spara en kopia.`)) {
      return
    }
    try {
      await api.deleteAllCooperatives()
      setError(null)
      setSelected([])
      loadCooperatives()
      loadProperties() // Apartments are kept, now unlinked.
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Kunde inte ta bort föreningarna.')
    }
  }

  function onDocumentAdded(document: DocumentSummary) {
    if (document.cooperative_id) navigate(`/foreningar/${document.cooperative_id}`)
    else setError(`${document.original_filename}: ${document.extraction_messages.join(' ')}`)
  }

  return (
    <div className="stack" style={{ gap: '1.5rem' }}>
      <div>
        <h1>Översikt</h1>
        <p className="muted">
          Lägg till en bostad från en annons, och ladda upp föreningens årsredovisning för att se nyckeltal, risker och
          källor.
        </p>
      </div>

      <div className="grid-2">
        <section className="card stack">
          <h2>Analysera en förening</h2>
          <DocumentUploader onAdded={onDocumentAdded} />
        </section>
        <section className="card stack">
          <h2>Analysera en bostad</h2>
          <ListingImporter onAdded={(property) => navigate(`/bostader/${property.id}`)} />
        </section>
      </div>

      <section>
        <div className="spread">
          <h2>Bostäder</h2>
          <span className="row">
            {properties && properties.length >= 2 && (
              <span className="small muted">Bocka i 2–{MAX_COMPARED_PROPERTIES} bostäder för att jämföra dem</span>
            )}
            {properties && properties.length > 0 && (
              <button className="danger small" onClick={() => deleteAllProperties(properties.length)}>
                Ta bort alla
              </button>
            )}
          </span>
        </div>
        {propertyError && <div className="notice error">{propertyError}</div>}
        {properties === null && <p className="muted">Laddar …</p>}
        {properties?.length === 0 && <p className="muted">Inga bostäder ännu. Lägg till en annons ovan.</p>}
        {properties && properties.length > 0 && (
          <ul className="list card" style={{ padding: '0 1.25rem' }}>
            {properties.map((property) => (
              <li key={property.id} className="spread">
                <label className="select-item">
                  <input
                    type="checkbox"
                    checked={selectedProperties.includes(property.id)}
                    disabled={!selectedProperties.includes(property.id) && selectedProperties.length >= MAX_COMPARED_PROPERTIES}
                    onChange={() => setSelectedProperties((current) => toggleId(current, property.id, MAX_COMPARED_PROPERTIES))}
                    aria-label={`Välj ${property.address ?? property.title ?? 'bostaden'} för jämförelse`}
                  />
                  <div>
                    <Link to={`/bostader/${property.id}`}>
                      <strong>{property.address ?? property.title ?? 'Bostad utan adress'}</strong>
                    </Link>
                    <div className="small muted">
                      {[
                        property.asking_price ? `${new Intl.NumberFormat('sv-SE').format(property.asking_price)} kr` : 'Pris saknas',
                        property.living_area ? `${property.living_area} m²` : null,
                        property.rooms ? `${String(property.rooms).replace('.', ',')} rum` : null,
                        property.monthly_fee ? `${new Intl.NumberFormat('sv-SE').format(property.monthly_fee)} kr/mån` : null,
                        property.cooperative_name,
                      ]
                        .filter(Boolean)
                        .join(' · ')}
                    </div>
                  </div>
                </label>
                <span className="row">
                  {property.cooperative_score !== null || property.cooperative_score_label ? (
                    <ScoreBadge score={property.cooperative_score} label={property.cooperative_score_label} prefix="Förening: " />
                  ) : (
                    <span className="badge">Ingen förening kopplad</span>
                  )}
                  <DeleteRowButton name={propertyName(property)} onClick={() => deleteProperty(property)} />
                </span>
              </li>
            ))}
          </ul>
        )}
        <CompareBar
          count={selectedProperties.length}
          max={MAX_COMPARED_PROPERTIES}
          singular="bostad"
          plural="bostäder"
          onClear={() => setSelectedProperties([])}
          onCompare={() => navigate(`/jamfor/bostader?ids=${selectedProperties.join(',')}`)}
        />
      </section>

      <section>
        <div className="spread">
          <h2>Föreningar</h2>
          <span className="row">
            {cooperatives && cooperatives.length >= 2 && (
              <span className="small muted">Bocka i 2–{MAX_COMPARED_COOPERATIVES} föreningar för att jämföra dem</span>
            )}
            {cooperatives && cooperatives.length > 0 && (
              <button className="danger small" onClick={() => deleteAllCooperatives(cooperatives.length)}>
                Ta bort alla
              </button>
            )}
          </span>
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
                    onChange={() => setSelected((current) => toggleId(current, cooperative.id, MAX_COMPARED_COOPERATIVES))}
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
                <span className="row">
                  <ScoreBadge score={cooperative.score} label={cooperative.score_label} />
                  <DeleteRowButton name={cooperative.name} onClick={() => deleteCooperative(cooperative)} />
                </span>
              </li>
            ))}
          </ul>
        )}
        <CompareBar
          count={selected.length}
          max={MAX_COMPARED_COOPERATIVES}
          singular="förening"
          plural="föreningar"
          onClear={() => setSelected([])}
          onCompare={() => navigate(`/jamfor?ids=${selected.join(',')}`)}
        />
      </section>
    </div>
  )
}

/** The × that deletes one row; it asks before deleting. */
function DeleteRowButton({ name, onClick }: { name: string; onClick: () => void }) {
  return (
    <button className="icon-button" onClick={onClick} title={`Ta bort ${name}`} aria-label={`Ta bort ${name}`}>
      ×
    </button>
  )
}
