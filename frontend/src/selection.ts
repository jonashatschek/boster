// Selecting items to compare.
/** Adds or removes `id`, never going above `max`. */
export function toggleId(current: number[], id: number, max: number): number[] {
  if (current.includes(id)) return current.filter((selectedId) => selectedId !== id)
  return current.length < max ? [...current, id] : current
}
