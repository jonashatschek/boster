import type { TransportInfo, TransportStop } from '../api'
import { formatDate } from '../format'
import type { TransportLookup } from '../transport/useTransportLookup'
import { StatusBadge } from './Badges'

interface Props {
  transport: TransportInfo
  lookup: TransportLookup
}

const STOP_STATUS_LABELS = { extracted: 'Från Trafiklab/OpenStreetMap' } as const

/** Nearest metro, local train and bus stop, with the walk there. The page runs the lookup. */
export function TransportSection({ transport, lookup }: Props) {
  const { busy, error, hasKey: key } = lookup

  // Types without a stop within walking distance are left out of the list.
  const found = transport.stops.filter((stop) => stop.walking_metres !== null && stop.walking_seconds !== null)

  return (
    <section className="card stack">
      <div className="spread">
        <h2>Kollektivtrafik</h2>
        {/* Only offered after a failure that a retry can fix. A missing house number needs a corrected
            address instead, which starts a new lookup by itself. */}
        {key && ((transport.status === 'failed' && transport.house_level !== false) || error) && (
          <button onClick={lookup.retry} disabled={busy}>
            {busy ? 'Hämtar …' : 'Hämta igen'}
          </button>
        )}
      </div>

      {transport.status === 'unavailable' ? (
        <div className="notice warning">{transport.message}</div>
      ) : !key ? (
        <div className="notice warning">
          Den här versionen av Boster saknar en nyckel till Trafiklab, så kollektivtrafiken kan inte hämtas.
        </div>
      ) : (
        <>
          {busy && <div className="notice">Hämtar hållplatser och gångvägar …</div>}
          {error && <div className="notice error">{error}</div>}
          {transport.status === 'failed' && <div className="notice error">{transport.message}</div>}
          {transport.status === 'skipped' && !busy && (
            <div className="stack" style={{ gap: '0.5rem' }}>
              <p>Ingen adress är vald, så kollektivtrafiken har inte hämtats.</p>
              <div>
                <button onClick={lookup.retry}>Välj adress</button>
              </div>
            </div>
          )}
          {transport.status === 'stale' && !busy && (
            <div className="notice warning">
              Adressen har ändrats sedan hållplatserna hämtades (då: ”{transport.looked_up_query}”). Uppgifterna nedan
              gäller den gamla adressen.
            </div>
          )}
          {found.length > 0 && (
            <ul className="list">
              {found.map((stop) => (
                <StopRow key={stop.type} stop={stop} />
              ))}
            </ul>
          )}
          {transport.stops.length > 0 && found.length === 0 && (
            <p>Ingen tunnelbana, pendeltåg/lokaltåg eller buss inom 2 km gångavstånd.</p>
          )}
          {found.length > 0 && (
            <p className="small muted">
              Gångavstånd och tid till den närmaste hållplatsen fågelvägen av varje slag. Tiden kommer från
              ruttjänsten och förutsätter normal gångtakt. Pendeltåg/lokaltåg omfattar även t.ex. Roslagsbanan och
              Saltsjöbanan.
            </p>
          )}
          {transport.retrieved_at && transport.status !== 'skipped' && (
            <div className="small muted stack" style={{ gap: '0.2rem' }}>
              <span>
                Sökt adress: ”{transport.looked_up_query}”
                {transport.place_label && <> → hittad som ”{transport.place_label}”</>}
              </span>
              <span>
                {found.length > 0 ? transport.source : 'Adressen: OpenStreetMap (Nominatim).'} Hämtad{' '}
                {formatDate(transport.retrieved_at)}.
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
      </p>
    </section>
  )
}

function StopRow({ stop }: { stop: TransportStop }) {
  return (
    <li className="stack" style={{ gap: '0.2rem' }}>
      <div className="spread">
        <span className="small muted">{stop.label}</span>
        <span>
          <strong>{stop.name}</strong> {formatMetres(stop.walking_metres!)} (ca{' '}
          {Math.max(1, Math.round(stop.walking_seconds! / 60))} min) till fots
        </span>
      </div>
      <div>
        <StatusBadge status={stop.status} labels={STOP_STATUS_LABELS} />
      </div>
    </li>
  )
}

function formatMetres(metres: number): string {
  return `${new Intl.NumberFormat('sv-SE').format(metres)} m`
}
