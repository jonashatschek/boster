import { useEffect, useRef, useState, type FormEvent } from 'react'
import { ApiError, type TransportInfo, type TransportStop } from '../api'
import { formatDate } from '../format'
import { loadTrafiklabKey, runTransportLookup, saveTrafiklabKey } from '../transport/runLookup'
import { StatusBadge } from './Badges'

interface Props {
  propertyId: number
  transport: TransportInfo
  onChange: (transport: TransportInfo, propertyId: number) => void
}

const STOP_STATUS_LABELS = { extracted: 'Från Trafiklab/OpenStreetMap' } as const
// Fetched automatically when there is no result yet, or the address has changed since.
const AUTOMATIC = new Set<TransportInfo['status']>(['not_fetched', 'stale', 'pending'])

/** Nearest metro, local train and bus stop, with the walk there. Fetched automatically. */
export function TransportSection({ propertyId, transport, onChange }: Props) {
  const [key, setKey] = useState<string | null>(loadTrafiklabKey)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // Each address is fetched automatically at most once per visit, so a failure can't loop.
  const attempted = useRef(new Set<string>())

  async function fetchTransport() {
    if (!key) return
    setBusy(true)
    setError(null)
    try {
      onChange(await runTransportLookup(propertyId, key), propertyId)
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Kollektivtrafiken kunde inte hämtas.')
    } finally {
      setBusy(false)
    }
  }

  const autoQuery = key && AUTOMATIC.has(transport.status) && transport.query ? transport.query : null
  useEffect(() => {
    if (!autoQuery || busy || attempted.current.has(autoQuery)) return
    attempted.current.add(autoQuery)
    void fetchTransport()
    // fetchTransport only changes with the key, which is part of autoQuery's condition.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoQuery, busy])

  function changeKey(newKey: string | null) {
    saveTrafiklabKey(newKey)
    setKey(newKey)
  }

  return (
    <section className="card stack">
      <div className="spread">
        <h2>Kollektivtrafik</h2>
        {key && transport.status !== 'unavailable' && (
          <button onClick={fetchTransport} disabled={busy}>
            {busy ? 'Hämtar …' : 'Hämta igen'}
          </button>
        )}
      </div>

      {transport.status === 'unavailable' ? (
        <div className="notice warning">{transport.message}</div>
      ) : !key ? (
        <KeyForm onSave={changeKey} />
      ) : (
        <>
          {busy && <div className="notice">Hämtar hållplatser och gångvägar …</div>}
          {error && <div className="notice error">{error}</div>}
          {transport.status === 'failed' && <div className="notice error">{transport.message}</div>}
          {transport.status === 'stale' && !busy && (
            <div className="notice warning">
              Adressen har ändrats sedan hållplatserna hämtades (då: ”{transport.looked_up_query}”). Uppgifterna nedan
              gäller den gamla adressen.
            </div>
          )}
          {transport.house_level === false && transport.message && transport.status !== 'failed' && (
            <div className="notice warning">{transport.message}</div>
          )}
          {transport.stops.length > 0 && (
            <ul className="list">
              {transport.stops.map((stop) => (
                <StopRow key={stop.type} stop={stop} />
              ))}
            </ul>
          )}
          {transport.stops.length > 0 && (
            <p className="small muted">
              Gångavstånd och tid till den närmaste hållplatsen fågelvägen av varje slag. Tiden kommer från
              ruttjänsten och förutsätter normal gångtakt. Pendeltåg/lokaltåg omfattar även t.ex. Roslagsbanan och
              Saltsjöbanan.
            </p>
          )}
          {transport.retrieved_at && (
            <div className="small muted stack" style={{ gap: '0.2rem' }}>
              <span>
                Sökt adress: ”{transport.looked_up_query}”
                {transport.place_label && <> → hittad som ”{transport.place_label}”</>}
              </span>
              <span>
                {transport.source} Hämtad {formatDate(transport.retrieved_at)}.
              </span>
            </div>
          )}
        </>
      )}

      <p className="small muted">
        Adressen skickas till OpenStreetMap och Trafiklab för att hitta hållplatser och gångvägar. Kartdata ©{' '}
        <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">
          OpenStreetMap-bidragsgivare
        </a>
        .
        {key && (
          <>
            {' '}
            <button className="link" onClick={() => changeKey(null)}>
              Ta bort Trafiklab-nyckeln
            </button>
          </>
        )}
      </p>
    </section>
  )
}

function StopRow({ stop }: { stop: TransportStop }) {
  return (
    <li className="stack" style={{ gap: '0.2rem' }}>
      <div className="spread">
        <span className="small muted">{stop.label}</span>
        {stop.walking_metres === null || stop.walking_seconds === null ? (
          <span className="missing">Saknas</span>
        ) : (
          <span>
            <strong>{stop.name}</strong>{' '}
            {formatMetres(stop.walking_metres)} (ca {Math.max(1, Math.round(stop.walking_seconds / 60))} min) till fots
          </span>
        )}
      </div>
      {stop.walking_metres !== null ? (
        <div>
          <StatusBadge status={stop.status} labels={STOP_STATUS_LABELS} />
        </div>
      ) : (
        stop.note && <span className="small muted">{stop.note}</span>
      )}
    </li>
  )
}

function formatMetres(metres: number): string {
  return `${new Intl.NumberFormat('sv-SE').format(metres)} m`
}

function KeyForm({ onSave }: { onSave: (key: string) => void }) {
  const [draft, setDraft] = useState('')

  function submit(event: FormEvent) {
    event.preventDefault()
    if (draft.trim()) onSave(draft.trim())
  }

  return (
    <form className="stack" onSubmit={submit}>
      <p className="small">
        För att hitta hållplatser behövs en egen, gratis nyckel till Trafiklabs API ResRobot. Skapa ett konto på{' '}
        <a href="https://www.trafiklab.se" target="_blank" rel="noreferrer">
          trafiklab.se
        </a>
        , lägg till ett projekt med ”ResRobot v2.1” och klistra in nyckeln här. Nyckeln sparas bara i den här
        webbläsaren och ingår inte i en export.
      </p>
      <div className="input-row">
        <input
          type="password"
          autoComplete="off"
          placeholder="Trafiklab-nyckel (ResRobot v2.1)"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          aria-label="Trafiklab-nyckel"
        />
        <button type="submit" className="primary" disabled={!draft.trim()}>
          Spara och hämta
        </button>
      </div>
    </form>
  )
}
