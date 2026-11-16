// Reads the text of each PDF page with pdf.js, in the shape the Python extraction
// expects (backend/app/documents/pdf_layout.py, PageText): the plain text, and each
// word with its box, (x0, y0, x1, y1, text) in points with the origin at the top left.

export interface PageText {
  text: string
  words: [number, number, number, number, string][]
}

interface Pending {
  x0: number
  x1: number
  y0: number
  y1: number
  text: string
  baseline: number
}

export async function readPageText(data: ArrayBuffer): Promise<PageText[]> {
  const pdfjs = await import('pdfjs-dist')
  const { default: workerUrl } = await import('pdfjs-dist/build/pdf.worker.min.mjs?url')
  pdfjs.GlobalWorkerOptions.workerSrc = workerUrl

  const loading = pdfjs.getDocument({ data: new Uint8Array(data.slice(0)) })
  try {
    const document = await loading.promise
    const pages: PageText[] = []
    for (let number = 1; number <= document.numPages; number++) {
      const page = await document.getPage(number)
      const viewport = page.getViewport({ scale: 1 })
      const content = await page.getTextContent()
      pages.push(wordsOfPage(content, viewport.transform, pdfjs.Util.transform))
      page.cleanup()
    }
    return pages
  } finally {
    await loading.destroy()
  }
}

type TextContent = Awaited<ReturnType<import('pdfjs-dist').PDFPageProxy['getTextContent']>>
type Transform = (a: number[], b: number[]) => number[]

function wordsOfPage(content: TextContent, viewportTransform: number[], multiply: Transform): PageText {
  const words: PageText['words'] = []
  let text = ''
  let pending: Pending | null = null // A word can continue across several text items.

  const flush = () => {
    if (pending && pending.text.trim()) words.push([pending.x0, pending.y0, pending.x1, pending.y1, pending.text])
    pending = null
  }

  for (const item of content.items) {
    if (!('str' in item)) continue
    text += item.str + (item.hasEOL ? '\n' : '')
    if (!item.str) {
      if (item.hasEOL) flush()
      continue
    }
    const matrix = multiply(viewportTransform, item.transform)
    const size = Math.hypot(matrix[2], matrix[3]) || Math.hypot(matrix[0], matrix[1])
    const style = content.styles[item.fontName] ?? {}
    // Some fonts report no metrics; typical values keep the word boxes sensible.
    const ascent = Number.isFinite(style.ascent) && style.ascent > 0 ? style.ascent : 0.8
    const descent = Number.isFinite(style.descent) && style.descent < 0 ? style.descent : -0.2
    const baseline = matrix[5]
    const y0 = baseline - ascent * size
    const y1 = baseline - descent * size
    const x = matrix[4]
    const width = item.width * Math.hypot(viewportTransform[0], viewportTransform[1])
    if (![x, y0, y1, width].every(Number.isFinite)) continue
    const charWidth = width / item.str.length

    // Continue the pending word only if this item touches it on the same baseline.
    // A raised footnote marker right after a number has another baseline, and stays apart.
    if (pending) {
      const previous: Pending = pending
      if (Math.abs(previous.baseline - baseline) > size * 0.3 || x - previous.x1 > size * 0.15 || x < previous.x1 - size) flush()
    }

    let start = 0
    while (start < item.str.length) {
      if (/\s/.test(item.str[start])) {
        flush()
        start++
        continue
      }
      let end = start
      while (end < item.str.length && !/\s/.test(item.str[end])) end++
      const part = item.str.slice(start, end)
      const x0 = x + start * charWidth
      const x1 = x + end * charWidth
      if (pending && start === 0) {
        const current: Pending = pending
        current.text += part
        current.x1 = x1
        current.y0 = Math.min(current.y0, y0)
        current.y1 = Math.max(current.y1, y1)
      } else {
        flush()
        pending = { x0, x1, y0, y1, text: part, baseline }
      }
      start = end
    }
    if (item.hasEOL) flush()
  }
  flush()
  return { text, words }
}
