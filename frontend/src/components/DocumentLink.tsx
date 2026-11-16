import type { MouseEvent, ReactNode } from 'react'
import { api } from '../api'

// The PDFs are stored in this browser, not on a server, so a link is made on demand.
const objectUrls = new Map<number, Promise<string>>()

function fileUrl(documentId: number): Promise<string> {
  let url = objectUrls.get(documentId)
  if (!url) {
    url = api.documentFileUrl(documentId)
    url.catch(() => objectUrls.delete(documentId))
    objectUrls.set(documentId, url)
  }
  return url
}

/** Opens a stored PDF in a new tab, at the given page when the browser's PDF viewer supports it. */
export function DocumentLink({ documentId, page, children }: { documentId: number; page?: number | null; children: ReactNode }) {
  async function open(event: MouseEvent) {
    event.preventDefault()
    // Open the tab right away: browsers block tabs opened after waiting for something.
    const tab = window.open('', '_blank')
    try {
      const url = (await fileUrl(documentId)) + (page ? `#page=${page}` : '')
      if (tab) tab.location.href = url
      else window.location.href = url
    } catch {
      tab?.close()
      alert('Dokumentet kunde inte öppnas.')
    }
  }

  return (
    <a href="#" onClick={open}>
      {children}
    </a>
  )
}
