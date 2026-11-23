import { useState } from 'react'
import { api, ApiError, type CooperativeOverview, type MaintenanceAnswer } from '../api'
import { formatDate } from '../format'
import { DocumentLink } from './DocumentLink'

const CHOICES: { value: MaintenanceAnswer; label: string }[] = [
  { value: 'yes', label: 'Ja' },
  { value: 'no', label: 'Nej' },
  { value: 'unknown', label: 'Vet inte' },
]

/**
 * The user's answers about maintenance coming up, with the report's own passages as evidence. Boster cannot tell
 * from the text whether work is done or planned, so only these answers count in the score.
 */
export function MaintenanceQuestions({
  overview,
  onChange,
}: {
  overview: CooperativeOverview
  onChange: (overview: CooperativeOverview) => void
}) {
  const [saving, setSaving] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function save(name: string, answer: MaintenanceAnswer) {
    if (saving) return // One save at a time; the question stays enabled so keyboard focus is kept.
    setSaving(name)
    setError(null)
    try {
      onChange(await api.answerMaintenance(overview.cooperative.id, name, answer))
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Kunde inte spara svaret.')
    } finally {
      setSaving(null)
    }
  }

  return (
    <section className="card stack">
      <h2>Kommande underhåll</h2>
      <p className="small muted">
        Boster kan inte avgöra av texten om arbetet är gjort eller planerat, så här svarar du själv, till exempel efter att
        ha läst underlaget nedan eller frågat föreningen. Bara dina svar räknas i poängen; Vet inte räknas inte.
      </p>
      {error && <div className="notice error">{error}</div>}
      {overview.maintenance.map((question) => {
        const passages = overview.findings.filter((finding) => finding.topic === question.topic)
        return (
          <fieldset key={question.name} className="maintenance-question stack" aria-busy={saving === question.name}>
            <legend>
              <strong>{question.label}</strong>
            </legend>
            <div>{question.question}</div>
            <div className="row">
              {CHOICES.map((choice) => (
                <label key={choice.value} className="row" style={{ gap: '0.3rem' }}>
                  <input
                    type="radio"
                    name={`maintenance-${question.name}`}
                    checked={question.answer === choice.value}
                    onChange={() => save(question.name, choice.value)}
                  />
                  {choice.label}
                </label>
              ))}
              {question.answered_at && (
                <span className="small muted">Besvarat {formatDate(question.answered_at)}</span>
              )}
            </div>
            {passages.length > 0 ? (
              <details>
                <summary className="small">Underlag i dokumenten ({passages.length})</summary>
                <ul className="list small">
                  {passages.map((finding, index) => (
                    <li key={index}>
                      ”{finding.excerpt}”{' '}
                      <DocumentLink documentId={finding.document_id} page={finding.page}>
                        s. {finding.page}
                      </DocumentLink>
                    </li>
                  ))}
                </ul>
              </details>
            ) : (
              <p className="small muted">Inga stycken om {question.topic.toLowerCase()} hittades i dokumenten.</p>
            )}
          </fieldset>
        )
      })}
    </section>
  )
}
