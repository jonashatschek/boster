import { useRef, useState, type DragEvent } from 'react'
import { api, ApiError, type DocumentSummary } from '../api'

interface Props {
  onAdded: (document: DocumentSummary) => void
}

/** Add a cooperative document by drag and drop or file picker. */
export function DocumentUploader({ onAdded }: Props) {
  const fileInput = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function run(description: string, action: () => Promise<DocumentSummary>) {
    setBusy(description)
    setError(null)
    try {
      onAdded(await action())
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Något gick fel.')
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
        <div className="muted small">Filen läses här i webbläsaren och laddas inte upp någonstans.</div>
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
      {busy && <div className="notice">{busy}</div>}
      {error && <div className="notice error">{error}</div>}
    </div>
  )
}
