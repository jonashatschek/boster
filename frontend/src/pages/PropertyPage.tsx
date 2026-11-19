import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  api,
  ApiError,
  type CooperativeListItem,
  type DerivedValue,
  type PropertyField,
  type PropertyFieldValue,
  type PropertyOverview,
} from '../api'
import { ConcernBadge, StatusBadge } from '../components/Badges'
import { DocumentUploader } from '../components/DocumentUploader'
import { ListingDescription } from '../components/ListingDescription'
import { TransportSection } from '../components/TransportSection'
import { AddressChoice } from '../components/AddressChoice'
import { useTransportLookup } from '../transport/useTransportLookup'
import { formatDate, formatKronor, formatValue, LAND_TENURE_LABELS } from '../format'

const METHOD_LABELS: Record<string, string> = {
  text_label: 'Annonstext',
  text_pattern: 'Annonstext (tolkad)',
  structured_data: 'Annonssidans strukturerade data',
  meta_tag: 'Annonssidans metadata',
  manual: 'Manuellt angivet',
  address_choice: 'Vald adress',
}

const RETRIEVAL_LABELS: Record<PropertyOverview['retrieval_status'], string> = {
  fetched: 'Hämtad från annonssidan',
  pasted: 'Läst från inklistrad annonstext',
  fetch_failed: 'Annonsen kunde inte hämtas',
  manual: 'Manuellt inlagd',
}

const LISTING_STATUS_LABELS = { extracted: 'Från annonsen' } as const

// Shown as headline figures above the fact list.
const HEADLINE_FIELDS = ['asking_price', 'living_area', 'rooms', 'monthly_fee']

export function PropertyPage() {
  const id = Number(useParams().id)
  // A fresh instance per apartment: no state (or late lookup result) carries over to the next one.
  return <PropertyView key={id} id={id} />
}

function PropertyView({ id }: { id: number }) {
  const navigate = useNavigate()
  const [property, setProperty] = useState<PropertyOverview | null>(null)
  const [cooperatives, setCooperatives] = useState<CooperativeListItem[]>([])
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    api
      .getProperty(id)
      .then(setProperty)
      .catch((caught) => setError(caught instanceof ApiError ? caught.message : 'Kunde inte hämta bostaden.'))
    api.listCooperatives().then(setCooperatives)
  }, [id])

  useEffect(load, [load])

  // Runs before the early returns below (a hook). Null until this apartment has loaded.
  const lookup = useTransportLookup(
    id,
    property?.id === id ? property.transport : null,
    // A lookup that finishes after moving to another apartment must not overwrite that one.
    (transport, forId) =>
      setProperty((current) => (current && current.id === forId ? { ...current, transport } : current)),
    load,
  )

  if (error) return <div className="notice error">{error}</div>
  if (!property) return <p className="muted">Laddar …</p>

  const field = (key: string) => property.fields.find((f) => f.key === key)!
  const address = field('address').value as string | null
  const title = address ?? property.title ?? 'Bostad utan adress'
  const area = [field('neighborhood').value, field('municipality').value].filter(Boolean).join(', ')
  const municipality = field('municipality').value as string | null

  // The whole page waits while the address is ambiguous: the user picks it, enters the
  // municipality, or continues without public transport.
  const transport = property.transport
  const waitingForAddress =
    lookup.hasKey &&
    (transport.status === 'choose' ||
      (!municipality && ['not_fetched', 'pending', 'stale'].includes(transport.status)))
  if (waitingForAddress) {
    return (
      <div className="stack" style={{ gap: '1.5rem' }}>
        <div className="small">
          <Link to="/">← Översikt</Link>
        </div>
        <h1>{title}</h1>
        <AddressChoice
          transport={transport}
          municipality={municipality}
          lookup={lookup}
          onSetMunicipality={async (value) => {
            await act(() => api.updateProperty(property.id, { municipality: value }))
          }}
        />
      </div>
    )
  }

  async function act(action: () => Promise<PropertyOverview>) {
    setError(null)
    try {
      setProperty(await action())
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Något gick fel.')
    }
  }

  async function remove() {
    if (!confirm('Ta bort bostaden? Det går inte att ångra.')) return
    await api.deleteProperty(property!.id)
    navigate('/')
  }

  return (
    <div className="stack" style={{ gap: '1.5rem' }}>
      <div className="small">
        <Link to="/">← Översikt</Link>
      </div>

      <div className="spread">
        <div>
          <h1>{title}</h1>
          <div className="muted small">
            {area && `${area} · `}
            {RETRIEVAL_LABELS[property.retrieval_status]}
            {property.retrieved_at && ` ${formatDate(property.retrieved_at)}`}
            {property.source_url && (
              <>
                {' · '}
                <a href={property.source_url} target="_blank" rel="noreferrer">
                  Annonsen på {property.source_name}
                </a>
              </>
            )}
          </div>
        </div>
        <div className="row">
          <button className="danger" onClick={remove}>
            Ta bort
          </button>
        </div>
      </div>

      {property.retrieval_message && (
        <div className={`notice ${property.retrieval_status === 'fetch_failed' ? 'error' : 'warning'}`}>
          {property.retrieval_message}
        </div>
      )}

      <PasteText property={property} onChange={setProperty} open={property.retrieval_status === 'fetch_failed'} />

      <section className="headline-grid">
        {HEADLINE_FIELDS.map((key) => {
          const f = field(key)
          return (
            <div className="card headline" key={key}>
              <div className="small muted">{f.label}</div>
              <div className="headline-value">{f.value === null ? <span className="missing">Saknas</span> : formatField(f)}</div>
              {f.value !== null && <StatusBadge status={f.status} labels={LISTING_STATUS_LABELS} />}
            </div>
          )
        })}
      </section>

      <div className="grid-2" style={{ alignItems: 'start' }}>
        <section className="card stack">
          <h2>Uppgifter</h2>
          <p className="small muted">Klicka på Ändra för att rätta ett värde. Dina ändringar skrivs aldrig över av en ny analys.</p>
          <ul className="list">
            {property.fields
              .filter((f) => !['title'].includes(f.key))
              .map((f) => (
                <FieldRow key={f.key} propertyId={property.id} field={f} onChange={setProperty} />
              ))}
          </ul>
        </section>

        <div className="stack" style={{ gap: '1rem' }}>
          <section className="card stack">
            <h2>Beräknat</h2>
            <ul className="list">
              {property.derived.map((value) => (
                <DerivedRow key={value.key} value={value} />
              ))}
            </ul>
          </section>

          <CooperativeSection property={property} cooperatives={cooperatives} act={act} reload={load} />

          <TransportSection transport={property.transport} lookup={lookup} />
        </div>
      </div>

      <section className="card stack">
        <div className="spread">
          <h2>Mäklarens beskrivning</h2>
          <span className="badge">Påståenden från annonsen</span>
        </div>
        <p className="small muted">
          Återges ordagrant och är inte kontrollerat. ”Nyrenoverat” säger till exempel inget om när eller hur något
          gjordes. En analys av texten kommer i nästa steg.
        </p>
        {property.description.value ? (
          <ListingDescription text={String(property.description.value)} />
        ) : (
          <p className="muted">Ingen beskrivning hittades.</p>
        )}
      </section>
    </div>
  )
}

function formatField(f: PropertyField): string {
  const value = f.value
  if (value === null) return 'Saknas'
  if (f.kind === 'boolean') return value ? 'Ja' : 'Nej'
  if (f.key === 'asking_price') return `${new Intl.NumberFormat('sv-SE').format(value as number)} kr`
  if (f.key === 'monthly_fee') return `${new Intl.NumberFormat('sv-SE').format(value as number)} kr/mån`
  if (f.key === 'living_area') return `${String(value).replace('.', ',')} m²`
  if (f.key === 'rooms') return `${String(value).replace('.', ',')} rum`
  if (f.kind === 'date') return formatDate(String(value))
  return String(value)
}

function PasteText({ property, onChange, open }: { property: PropertyOverview; onChange: (p: PropertyOverview) => void; open: boolean }) {
  const [text, setText] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      onChange(await api.addPropertyText(property.id, text))
      setText('')
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Något gick fel.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <details className="card" open={open}>
      <summary>{open ? 'Klistra in annonsens text' : 'Klistra in annonstext igen (t.ex. om annonsen har ändrats)'}</summary>
      <form className="stack" onSubmit={submit} style={{ marginTop: '0.75rem' }}>
        <p className="small muted">
          Öppna annonsen i webbläsaren, markera allt (Ctrl+A), kopiera (Ctrl+C) och klistra in nedan. Värden du har ändrat
          själv behålls.
        </p>
        <textarea rows={6} value={text} onChange={(event) => setText(event.target.value)} aria-label="Annonstext" />
        <div>
          <button type="submit" className="primary" disabled={busy || text.trim().length < 20}>
            {busy ? 'Läser …' : 'Läs in text'}
          </button>
        </div>
        {error && <div className="notice error">{error}</div>}
      </form>
    </details>
  )
}

function FieldRow({ propertyId, field, onChange }: { propertyId: number; field: PropertyField; onChange: (p: PropertyOverview) => void }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')
  const [error, setError] = useState<string | null>(null)

  function startEditing() {
    setDraft(field.value === null ? '' : field.kind === 'boolean' ? String(field.value) : String(field.value))
    setEditing(true)
  }

  async function save(event: FormEvent) {
    event.preventDefault()
    setError(null)
    let value: PropertyFieldValue = draft.trim() === '' ? null : draft.trim()
    if (value !== null && (field.kind === 'number' || field.kind === 'integer')) {
      value = Number(String(value).replace(/\s/g, '').replace(',', '.'))
      if (!Number.isFinite(value)) {
        setError('Ange ett tal.')
        return
      }
    }
    if (field.kind === 'boolean') value = draft === '' ? null : draft === 'true'
    try {
      onChange(await api.updateProperty(propertyId, { [field.key]: value }))
      setEditing(false)
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Kunde inte spara.')
    }
  }

  async function verify() {
    try {
      onChange(await api.verifyPropertyField(propertyId, field.key))
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Något gick fel.')
    }
  }

  return (
    <li className="stack" style={{ gap: '0.3rem' }}>
      <div className="spread">
        <span className="muted small">{field.label}</span>
        <span className="row">
          {field.value === null ? <span className="missing">Saknas</span> : <strong>{formatField(field)}</strong>}
          {field.value !== null && <StatusBadge status={field.status} labels={LISTING_STATUS_LABELS} />}
          <button className="link small" onClick={startEditing}>
            Ändra
          </button>
        </span>
      </div>
      {(field.excerpt || field.note || field.method) && field.value !== null && (
        <details>
          <summary>Källa</summary>
          <div className="small stack" style={{ gap: '0.25rem', marginTop: '0.25rem' }}>
            {field.method && <span className="muted">{METHOD_LABELS[field.method] ?? field.method}</span>}
            {field.excerpt && <span>{field.excerpt}</span>}
            {field.note && <span className="notice warning">{field.note}</span>}
            {field.status === 'extracted' && (
              <button className="link small" onClick={verify} style={{ alignSelf: 'flex-start' }}>
                Markera som kontrollerad
              </button>
            )}
          </div>
        </details>
      )}
      {editing && (
        <form className="input-row" onSubmit={save}>
          {field.kind === 'boolean' ? (
            <select value={draft} onChange={(event) => setDraft(event.target.value)} aria-label={field.label}>
              <option value="">Okänt</option>
              <option value="true">Ja</option>
              <option value="false">Nej</option>
            </select>
          ) : (
            <input
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              type={field.kind === 'date' ? 'date' : 'text'}
              inputMode={field.kind === 'number' || field.kind === 'integer' ? 'decimal' : undefined}
              placeholder={field.unit ? `I ${field.unit}` : undefined}
              aria-label={field.label}
              autoFocus
            />
          )}
          <button type="submit" className="primary">
            Spara
          </button>
          <button type="button" onClick={() => setEditing(false)}>
            Avbryt
          </button>
        </form>
      )}
      {error && <div className="notice error">{error}</div>}
    </li>
  )
}

function DerivedRow({ value }: { value: DerivedValue }) {
  const unit = value.unit === 'kr' ? 'kr' : value.unit
  return (
    <li className="stack" style={{ gap: '0.3rem' }}>
      <div className="spread">
        <span className="small muted">{value.label}</span>
        {value.value === null ? (
          <span className="missing">Kan inte beräknas</span>
        ) : (
          <strong className="calculated-text">{formatDerived(value.value, unit)}</strong>
        )}
      </div>
      <details>
        <summary>Så beräknas det</summary>
        <div className="small stack" style={{ gap: '0.25rem', marginTop: '0.25rem' }}>
          <code>{value.formula}</code>
          {Object.entries(value.inputs).map(([name, formatted]) => (
            <span key={name}>
              {name}: {formatted}
            </span>
          ))}
          {value.missing_inputs.length > 0 && <span className="notice">Saknas: {value.missing_inputs.join(', ')}.</span>}
          {value.note && <span className="muted">{value.note}</span>}
        </div>
      </details>
    </li>
  )
}

function formatDerived(value: number, unit: string): string {
  if (unit === 'kr') return formatKronor(value)
  return `${new Intl.NumberFormat('sv-SE', { maximumFractionDigits: 0 }).format(value)} ${unit}`
}

function CooperativeSection({
  property,
  cooperatives,
  act,
  reload,
}: {
  property: PropertyOverview
  cooperatives: CooperativeListItem[]
  act: (action: () => Promise<PropertyOverview>) => void
  reload: () => void
}) {
  const linked = property.cooperative
  const nameInListing = property.fields.find((f) => f.key === 'cooperative_name')?.value as string | null

  if (linked) {
    return (
      <section className="card stack">
        <div className="spread">
          <h2>Föreningen</h2>
          <ConcernBadge level={linked.overall_level} label={`Samlat: ${linked.overall_label}`} />
        </div>
        <div>
          <Link to={`/foreningar/${linked.id}`}>
            <strong>{linked.name}</strong>
          </Link>
          <div className="small muted">
            Org.nr {linked.organisation_number ?? 'saknas'} · räkenskapsår {linked.fiscal_year ?? 'okänt'} · mark:{' '}
            {linked.land_tenure ? LAND_TENURE_LABELS[linked.land_tenure] : 'okänt'} · {linked.completeness_available} av{' '}
            {linked.completeness_total} viktiga uppgifter
          </div>
        </div>
        <ul className="list small">
          {linked.indicators
            .filter((indicator) => indicator.key !== 'land_tenure')
            .map((indicator) => (
              <li key={indicator.key} className="spread">
                <span>{indicator.label}</span>
                <span className="row">
                  {formatValue(indicator.value, indicator.unit ?? '')}
                  <ConcernBadge level={indicator.level} label={indicator.level_label} />
                </span>
              </li>
            ))}
        </ul>
        <div className="row small">
          <Link to={`/foreningar/${linked.id}`}>Visa hela analysen</Link>
          <button className="link small" onClick={() => act(() => api.linkPropertyCooperative(property.id, null))}>
            Fel förening? Ta bort kopplingen
          </button>
        </div>
      </section>
    )
  }

  return (
    <section className="card stack">
      <h2>Föreningen</h2>
      <p className="small">
        {nameInListing ? (
          <>
            Annonsen anger <strong>{nameInListing}</strong>, men den är inte kopplad till någon förening i Boster ännu.
          </>
        ) : (
          'Annonsen anger ingen förening.'
        )}
      </p>
      {property.cooperative_suggestions.length > 0 && (
        <div className="stack" style={{ gap: '0.4rem' }}>
          <span className="small muted">Liknande namn – kontrollera att det är samma förening (organisationsnummer):</span>
          {property.cooperative_suggestions.map((c) => (
            <div key={c.id} className="spread small">
              <span>
                {c.name} <span className="muted">{c.organisation_number}</span>
              </span>
              <button onClick={() => act(() => api.linkPropertyCooperative(property.id, c.id))}>Koppla</button>
            </div>
          ))}
        </div>
      )}
      {cooperatives.length > 0 && (
        <select
          value=""
          onChange={(event) => act(() => api.linkPropertyCooperative(property.id, Number(event.target.value)))}
          aria-label="Koppla till befintlig förening"
        >
          <option value="">Koppla till en förening i Boster …</option>
          {cooperatives.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
      )}
      <span className="small muted">…eller ladda upp föreningens årsredovisning:</span>
      <DocumentUploader
        onAdded={(document) => {
          if (document.cooperative_id) act(() => api.linkPropertyCooperative(property.id, document.cooperative_id))
          else reload()
        }}
      />
    </section>
  )
}
