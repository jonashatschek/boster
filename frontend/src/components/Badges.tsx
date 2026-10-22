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
