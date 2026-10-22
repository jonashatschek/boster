import { useState } from 'react'

interface Props {
  text: string
}

// Paragraphs shown before "Visa hela beskrivningen".
const COLLAPSED_PARAGRAPHS = 2
const SENTENCES_PER_PARAGRAPH = 3

/** The agent's description, verbatim, set as readable paragraphs. */
export function ListingDescription({ text }: Props) {
  const [expanded, setExpanded] = useState(false)
  const paragraphs = toParagraphs(text)
  const collapsible = paragraphs.length > COLLAPSED_PARAGRAPHS + 1
  const shown = collapsible && !expanded ? paragraphs.slice(0, COLLAPSED_PARAGRAPHS) : paragraphs

  return (
    <div className="listing-description">
      <blockquote className={collapsible && !expanded ? 'collapsed' : undefined}>
        {shown.map((paragraph, index) => (
          <p key={index}>{paragraph}</p>
        ))}
      </blockquote>
      {collapsible && (
        <button className="link" onClick={() => setExpanded(!expanded)} aria-expanded={expanded}>
          {expanded ? 'Visa mindre' : `Visa hela beskrivningen (${paragraphs.length - COLLAPSED_PARAGRAPHS} stycken till)`}
        </button>
      )}
    </div>
  )
}

/**
 * The paragraphs as written. A description saved as one long block (some listing pages
 * only provide that) is split every few sentences, only for display; no words change.
 */
function toParagraphs(text: string): string[] {
  const paragraphs = text
    .split(/\n\s*\n/)
    .map((p) => p.trim())
    .filter(Boolean)
  if (paragraphs.length > 1 || text.length < 500) return paragraphs

  const sentences = text.split(/(?<=[.!?])\s+(?=[A-ZÅÄÖ])/)
  const grouped: string[] = []
  for (let i = 0; i < sentences.length; i += SENTENCES_PER_PARAGRAPH) {
    grouped.push(sentences.slice(i, i + SENTENCES_PER_PARAGRAPH).join(' '))
  }
  return grouped
}
