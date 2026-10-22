import { useState, type FormEvent } from 'react'
import { api, ApiError, type PropertyOverview } from '../api'

interface Props {
  onAdded: (property: PropertyOverview) => void
}

/** Add an apartment from a listing link, or from the listing's text when the site blocks fetching. */
export function ListingImporter({ onAdded }: Props) {
  const [mode, setMode] = useState<'url' | 'text'>('url')
  const [url, setUrl] = useState('')
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      onAdded(mode === 'url' ? await api.addPropertyFromUrl(url.trim()) : await api.addPropertyFromText(text, url.trim()))
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Något gick fel.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="stack" onSubmit={submit}>
      <div className="segmented" role="group" aria-label="Hur vill du lägga till bostaden?">
        <button type="button" className={mode === 'url' ? 'selected' : ''} onClick={() => setMode('url')}>
          Länk
        </button>
        <button type="button" className={mode === 'text' ? 'selected' : ''} onClick={() => setMode('text')}>
          Klistra in text
        </button>
      </div>
      {mode === 'url' ? (
        <>
          <div className="input-row">
            <input
              type="url"
              placeholder="Länk till annons på Hemnet, Booli eller mäklarsida"
              value={url}
              onChange={(event) => setUrl(event.target.value)}
              aria-label="Annonslänk"
              required
            />
            <button type="submit" className="primary" disabled={busy || !url.trim()}>
              Analysera
            </button>
          </div>
          <p className="small muted">
            Hemnet och Booli tillåter inte automatisk hämtning. Då sparas länken och du kan klistra in annonsens text i
            nästa steg.
          </p>
        </>
      ) : (
        <>
          <textarea
            rows={6}
            placeholder="Öppna annonsen, markera allt (Ctrl+A), kopiera (Ctrl+C) och klistra in här"
            value={text}
            onChange={(event) => setText(event.target.value)}
            aria-label="Annonstext"
            required
          />
          <div className="input-row">
            <input
              type="url"
              placeholder="Länk till annonsen (valfritt)"
              value={url}
              onChange={(event) => setUrl(event.target.value)}
              aria-label="Annonslänk (valfritt)"
            />
            <button type="submit" className="primary" disabled={busy || text.trim().length < 20}>
              Analysera
            </button>
          </div>
        </>
      )}
      {busy && <div className="notice">{mode === 'url' ? 'Hämtar annonsen …' : 'Läser annonstexten …'}</div>}
      {error && <div className="notice error">{error}</div>}
    </form>
  )
}
