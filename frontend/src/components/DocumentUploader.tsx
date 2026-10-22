import { useRef, useState, type DragEvent, type FormEvent } from 'react'
import { api, ApiError, type DocumentSummary } from '../api'

interface Props {
  onAdded: (document: DocumentSummary) => void
}

/** Add a cooperative document by drag and drop, file picker or link. */
export function DocumentUploader({ onAdded }: Props) {
  const fileInput = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [url, setUrl] = useState('')

  /** Returns true when the document was added. */
  async function run(description: string, action: () => Promise<DocumentSummary>): Promise<boolean> {
    setBusy(description)
    setError(null)
    try {
      onAdded(await action())
      return true
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Något gick fel.')
      return false
    } finally {
      setBusy(null)
    }
  }

  function uploadFiles(files: FileList | null) {
    const file = files?.[0]
    if (!file) return
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      setError('Bara PDF-filer stöds.')
      return
    }
    run(`Analyserar ${file.name} …`, () => api.uploadDocument(file))
  }

  function onDrop(event: DragEvent) {
    event.preventDefault()
    setDragging(false)
    uploadFiles(event.dataTransfer.files)
  }

  function onSubmitUrl(event: FormEvent) {
    event.preventDefault()
    if (!url.trim()) return
    run('Hämtar och analyserar dokumentet …', () => api.addDocumentFromUrl(url.trim())).then((added) => {
      if (added) setUrl('')
    })
  }

  return (
    <div className="stack">
      <div
        className={`drop-zone${dragging ? ' active' : ''}`}
        role="button"
        tabIndex={0}
        onClick={() => fileInput.current?.click()}
        onKeyDown={(event) => event.key === 'Enter' && fileInput.current?.click()}
        onDragOver={(event) => {
          event.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
      >
        <strong>Släpp en PDF här</strong>
        <div className="muted small">eller klicka för att välja fil – årsredovisning, ekonomisk plan m.m.</div>
        <input
          ref={fileInput}
          type="file"
          accept="application/pdf,.pdf"
          hidden
          onChange={(event) => {
            uploadFiles(event.target.files)
            event.target.value = ''
          }}
        />
      </div>
      <form className="input-row" onSubmit={onSubmitUrl}>
        <input
          type="url"
          placeholder="…eller klistra in en länk till en PDF"
          value={url}
          onChange={(event) => setUrl(event.target.value)}
          aria-label="Länk till dokument"
        />
        <button type="submit" disabled={!!busy || !url.trim()}>
          Hämta
        </button>
      </form>
      {busy && <div className="notice">{busy}</div>}
      {error && <div className="notice error">{error}</div>}
    </div>
  )
}
