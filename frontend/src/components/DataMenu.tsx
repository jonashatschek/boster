import { useRef, useState } from 'react'
import { api, ApiError } from '../api'

/** Export all data to a file, or replace it with an exported file. The data lives only in this browser. */
export function DataMenu() {
  const fileInput = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)

  async function exportData() {
    setBusy(true)
    try {
      const blob = await api.exportData()
      const link = document.createElement('a')
      link.href = URL.createObjectURL(blob)
      link.download = `boster-${new Date().toISOString().slice(0, 10)}.zip`
      link.click()
      setTimeout(() => URL.revokeObjectURL(link.href), 60_000)
    } catch (caught) {
      alert(caught instanceof ApiError ? caught.message : 'Exporten misslyckades.')
    } finally {
      setBusy(false)
    }
  }

  async function importData(file: File | undefined) {
    if (!file) return
    if (!confirm(`Importera ${file.name}? All data i den här webbläsaren ersätts med innehållet i filen.`)) return
    setBusy(true)
    try {
      await api.importData(file)
      window.location.reload() // Every page shows the imported data.
    } catch (caught) {
      alert(caught instanceof ApiError ? caught.message : 'Importen misslyckades.')
      setBusy(false)
    }
  }

  return (
    <div className="row data-menu">
      <span className="muted small" title="Inget skickas till någon server. Exportera för att spara en kopia eller flytta till en annan dator.">
        Data sparas bara i den här webbläsaren
      </span>
      <button onClick={exportData} disabled={busy} title="Ladda ner all data som en fil">
        Exportera
      </button>
      <button onClick={() => fileInput.current?.click()} disabled={busy} title="Ersätt all data med en exporterad fil">
        Importera
      </button>
      <input
        ref={fileInput}
        type="file"
        accept=".zip,application/zip"
        hidden
        onChange={(event) => {
          importData(event.target.files?.[0])
          event.target.value = ''
        }}
      />
    </div>
  )
}
