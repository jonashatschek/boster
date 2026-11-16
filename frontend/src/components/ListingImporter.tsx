import { useState, type FormEvent } from 'react'
import { api, ApiError, type PropertyOverview } from '../api'

interface Props {
  onAdded: (property: PropertyOverview) => void
}

/** Add an apartment from the listing's text, pasted from the browser. The link is saved for reference. */
export function ListingImporter({ onAdded }: Props) {
  const [url, setUrl] = useState('')
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      onAdded(await api.addPropertyFromText(text, url.trim()))
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Något gick fel.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="stack" onSubmit={submit}>
      <textarea
        rows={6}
        placeholder="Öppna annonsen på Hemnet, Booli eller mäklarens sida, markera allt (Ctrl+A), kopiera (Ctrl+C) och klistra in här"
        value={text}
        onChange={(event) => setText(event.target.value)}
        aria-label="Annonstext"
        required
      />
      <div className="input-row">
        <input
          type="url"
          placeholder="Länk till annonsen (valfritt, sparas så att du hittar tillbaka)"
          value={url}
          onChange={(event) => setUrl(event.target.value)}
          aria-label="Annonslänk (valfritt)"
        />
        <button type="submit" className="primary" disabled={busy || text.trim().length < 20}>
          Analysera
        </button>
      </div>
      {busy && <div className="notice">Läser annonstexten …</div>}
      {error && <div className="notice error">{error}</div>}
    </form>
  )
}
