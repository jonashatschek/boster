import { useState, type FormEvent } from 'react'
import type { TransportInfo } from '../api'
import type { TransportLookup } from '../transport/useTransportLookup'

interface Props {
  transport: TransportInfo
  municipality: string | null
  lookup: TransportLookup
  onSetMunicipality: (municipality: string) => Promise<void>
}

/**
 * Shown instead of the apartment page while its address is ambiguous: the listing names no
 * municipality, or the street and number exist in several places. Boster never picks for the user.
 */
export function AddressChoice({ transport, municipality, lookup, onSetMunicipality }: Props) {
  const [typing, setTyping] = useState(false)
  const [draft, setDraft] = useState('')
  const [saving, setSaving] = useState(false)
  // An error ends the search; the user can then retry, enter the municipality or skip.
  const searching = lookup.busy || (['not_fetched', 'pending', 'stale'].includes(transport.status) && !lookup.error)

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!draft.trim()) return
    setSaving(true)
    try {
      await onSetMunicipality(draft.trim())
      setTyping(false)
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="card stack">
      <h2>Välj rätt adress</h2>
      <p>
        {municipality
          ? `Adressen ”${transport.query}” finns på flera ställen. Välj vilken som gäller för bostaden.`
          : `Annonsen anger ingen kommun för ”${transport.query}”. Välj vilken adress bostaden har.`}{' '}
        Valet behövs för att hitta kollektivtrafiken nära bostaden.
      </p>

      {searching && <div className="notice">Söker adresser …</div>}
      {lookup.error && !lookup.busy && (
        <div className="notice error spread">
          <span>{lookup.error}</span>
          <button onClick={lookup.retry}>Försök igen</button>
        </div>
      )}
      {transport.status === 'failed' && !searching && <div className="notice error">{transport.message}</div>}
      {transport.status === 'choose' && !searching && (
        <>
          {transport.message && <div className="notice warning">{transport.message}</div>}
          <div className="stack" style={{ gap: '0.5rem' }}>
            {transport.candidates.map((candidate, index) => (
              <button key={candidate.label} className="choice" onClick={() => lookup.choose(index)}>
                {candidate.label}
              </button>
            ))}
          </div>
          {transport.truncated && (
            <p className="small muted">
              Visar de {transport.candidates.length} första. Ange kommunen för att begränsa sökningen.
            </p>
          )}
          <p className="small muted">
            Kommunen du väljer sparas som ditt eget värde, med OpenStreetMap som källa.
          </p>
        </>
      )}

      {!searching &&
        (typing ? (
          <form className="input-row" onSubmit={submit}>
            <input
              autoFocus
              placeholder="Kommun, t.ex. Stockholms kommun"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              aria-label="Kommun"
            />
            <button type="submit" className="primary" disabled={saving || !draft.trim()}>
              Sök
            </button>
          </form>
        ) : (
          <div className="row">
            <button onClick={() => setTyping(true)}>Ingen av dessa – ange kommun själv</button>
            <button onClick={lookup.skip}>Fortsätt utan kollektivtrafik</button>
          </div>
        ))}

      <p className="small muted">
        Adressen skickas till OpenStreetMap för att hitta den. Kartdata ©{' '}
        <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">
          OpenStreetMap-bidragsgivare
        </a>
        .
      </p>
    </section>
  )
}
