import type { ConcernLevel, VerificationStatus } from '../api'
import { STATUS_DESCRIPTIONS, STATUS_LABELS } from '../format'

/** `labels` overrides the wording for some statuses, e.g. "Från annonsen" for listing values. */
export function StatusBadge({ status, labels }: { status: VerificationStatus; labels?: Partial<Record<VerificationStatus, string>> }) {
  return (
    <span className={`badge status-${status}`} title={STATUS_DESCRIPTIONS[status]}>
      {labels?.[status] ?? STATUS_LABELS[status]}
    </span>
  )
}

export function ConcernBadge({ level, label }: { level: ConcernLevel; label: string }) {
  return <span className={`badge ${level}`}>{label}</span>
}

/**
 * A cooperative's 0–100 score, deliberately without verdict colours: it is a summary of rules
 * of thumb, explained on the cooperative page, not a credit rating.
 */
export function ScoreBadge({ score, label, prefix = '' }: { score: number | null; label: string | null; prefix?: string }) {
  const text = score !== null ? `${score} / 100` : (label ?? 'Otillräcklig information')
  return (
    <span className="badge score" title="Poäng 0–100 enligt tumregler, med förklaring på föreningens sida. Inget kreditbetyg.">
      {prefix}
      {text}
    </span>
  )
}
