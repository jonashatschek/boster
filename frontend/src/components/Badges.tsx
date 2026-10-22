import type { ConcernLevel, VerificationStatus } from '../api'
import { STATUS_DESCRIPTIONS, STATUS_LABELS } from '../format'

export function StatusBadge({ status }: { status: VerificationStatus }) {
  return (
    <span className={`badge status-${status}`} title={STATUS_DESCRIPTIONS[status]}>
      {STATUS_LABELS[status]}
    </span>
  )
}

export function ConcernBadge({ level, label }: { level: ConcernLevel; label: string }) {
  return <span className={`badge ${level}`}>{label}</span>
}
