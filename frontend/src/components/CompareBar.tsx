/** Sticky bar shown while items are ticked for comparison. */
export function CompareBar({
  count,
  max,
  singular,
  plural,
  onClear,
  onCompare,
}: {
  count: number
  max: number
  singular: string
  plural: string
  onClear: () => void
  onCompare: () => void
}) {
  if (count === 0) return null
  return (
    <div className="compare-bar">
      <span>
        {count} {count === 1 ? `${singular} vald` : `${plural} valda`}
        {count === 1 && <span className="muted"> – välj minst en till</span>}
        {count === max && <span className="muted"> (max)</span>}
      </span>
      <span className="row">
        <button onClick={onClear}>Rensa</button>
        <button className="primary" disabled={count < 2} onClick={onCompare}>
          Jämför
        </button>
      </span>
    </div>
  )
}

