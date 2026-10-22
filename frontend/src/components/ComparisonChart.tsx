import { useState } from 'react'
import { Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { ComparedCooperative, ComparisonRow } from '../api'
import { formatValue } from '../format'

interface Props {
  row: ComparisonRow
  cooperatives: ComparedCooperative[]
}

export const SERIES_COLORS = ['var(--series-1)', 'var(--series-2)', 'var(--series-3)', 'var(--series-4)']

const compact = new Intl.NumberFormat('sv-SE', { notation: 'compact', maximumFractionDigits: 1 })
const axisTick = { fill: 'var(--text-muted)', fontSize: 12 }
const tooltipStyle = { background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8 }

/**
 * One key figure across cooperatives: the latest year as bars, or the history as
 * one line per cooperative. Years without data stay empty, never interpolated.
 */
export function ComparisonChart({ row, cooperatives }: Props) {
  const [view, setView] = useState<'latest' | 'history'>('latest')
  const unitLabel = row.unit === 'kr' ? 'kronor' : row.unit.replace('kvm', 'm²')

  const latest = cooperatives.map((cooperative, index) => ({
    name: cooperative.name,
    label: `${shortName(cooperative.name)} (${cooperative.fiscal_year ?? '?'})`,
    value: row.cells[index].value,
    color: SERIES_COLORS[index],
  }))

  const years = Object.values(row.history).flatMap((points) => points.map((p) => p.fiscal_year))
  const first = Math.min(...years)
  const last = Math.max(...years)
  const history = []
  for (let year = first; year <= last; year++) {
    const point: Record<string, number | string | null> = { year: String(year) }
    cooperatives.forEach((cooperative) => {
      const found = row.history[cooperative.id]?.find((p) => p.fiscal_year === year)
      point[String(cooperative.id)] = found?.value ?? null
    })
    history.push(point)
  }

  return (
    <div className="card chart-card">
      <div className="spread">
        <h3>{row.label}</h3>
        <div className="segmented" role="group" aria-label="Diagramtyp">
          <button className={view === 'latest' ? 'selected' : ''} onClick={() => setView('latest')}>
            Senaste år
          </button>
          <button className={view === 'history' ? 'selected' : ''} onClick={() => setView('history')}>
            Över tid
          </button>
        </div>
      </div>
      <div className="muted small">
        {unitLabel}
        {view === 'history' && years.length > 0 && ` · räkenskapsår ${first}–${last}`}
      </div>
      <div style={{ width: '100%', height: 220, marginTop: '0.5rem' }}>
        <ResponsiveContainer>
          {view === 'latest' ? (
            <BarChart data={latest} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
              <CartesianGrid stroke="var(--border)" vertical={false} />
              <XAxis dataKey="label" tick={false} stroke="var(--border)" height={4} />
              <YAxis width={56} tick={axisTick} stroke="var(--border)" tickFormatter={(v: number) => compact.format(v)} />
              <Tooltip
                contentStyle={tooltipStyle}
                cursor={{ fill: 'var(--surface-muted)' }}
                formatter={(value) => [formatValue(value as number | null, row.unit), row.label]}
              />
              <Bar dataKey="value" isAnimationActive={false} radius={[4, 4, 0, 0]}>
                {latest.map((d) => (
                  <Cell key={d.name} fill={d.color} />
                ))}
              </Bar>
            </BarChart>
          ) : (
            <LineChart data={history} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
              <CartesianGrid stroke="var(--border)" vertical={false} />
              <XAxis dataKey="year" tick={axisTick} stroke="var(--border)" />
              <YAxis width={56} tick={axisTick} stroke="var(--border)" tickFormatter={(v: number) => compact.format(v)} />
              <Tooltip
                contentStyle={tooltipStyle}
                labelFormatter={(label) => `Räkenskapsår ${label}`}
                formatter={(value, name) => [
                  formatValue(value as number | null, row.unit),
                  cooperatives.find((c) => String(c.id) === name)?.name ?? name,
                ]}
              />
              <Legend
                formatter={(value) => shortName(cooperatives.find((c) => String(c.id) === value)?.name ?? String(value))}
                wrapperStyle={{ fontSize: 12 }}
              />
              {cooperatives.map((cooperative, index) => (
                <Line
                  key={cooperative.id}
                  dataKey={String(cooperative.id)}
                  stroke={SERIES_COLORS[index]}
                  strokeWidth={2}
                  dot={{ r: 3, fill: SERIES_COLORS[index] }}
                  connectNulls={false}
                  isAnimationActive={false}
                />
              ))}
            </LineChart>
          )}
        </ResponsiveContainer>
      </div>
      {view === 'latest' && (
        <div className="chart-key small">
          {latest.map((d) => (
            <span key={d.name} className="row" style={{ gap: '0.3rem' }}>
              <span className="swatch" style={{ background: d.color }} aria-hidden />
              {d.label}
              {d.value === null && <span className="muted"> – saknas</span>}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

/** "HSB Bostadsrättsförening Segelflygaren i Stockholm" → "Segelflygaren", to fit chart axes. */
export function shortName(name: string): string {
  const stripped = name
    .replace(/^(HSB|Riksbyggens)\s+/i, '')
    .replace(/^(Brf|BRF|Bostadsrätts?förening(en)?)\s+/i, '')
    .replace(/\s+i\s+\S+$/, '')
  return stripped.length > 18 ? `${stripped.slice(0, 17)}…` : stripped
}
