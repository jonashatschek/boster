import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { MetricSeries } from '../api'
import { formatValue, STATUS_LABELS } from '../format'

interface Props {
  series: MetricSeries
}

const compact = new Intl.NumberFormat('sv-SE', { notation: 'compact', maximumFractionDigits: 1 })

/**
 * A metric over time. Every fiscal year between the first and last data point gets a
 * slot on the axis; years without data stay empty instead of being interpolated.
 */
export function MetricChart({ series }: Props) {
  const byYear = new Map(series.values.map((v) => [v.fiscal_year, v]))
  const years = series.values.map((v) => v.fiscal_year)
  const first = Math.min(...years)
  const last = Math.max(...years)
  const data = []
  for (let year = first; year <= last; year++) {
    const point = byYear.get(year)
    data.push({ year: String(year), value: point?.display_value ?? null, status: point?.display_status ?? 'missing' })
  }
  const missingYears = data.filter((d) => d.value === null).map((d) => d.year)
  const special = series.values.filter((v) => v.display_status === 'calculated' || v.display_status === 'conflicting')

  return (
    <div className="card chart-card">
      <h3>{series.label}</h3>
      <div className="muted small">
        {series.unit === 'kr' ? 'kronor' : series.unit.replace('kvm', 'm²')} · räkenskapsår {first}–{last}
      </div>
      <div style={{ width: '100%', height: 200, marginTop: '0.5rem' }}>
        <ResponsiveContainer>
          <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="var(--border)" vertical={false} />
            <XAxis dataKey="year" tick={{ fill: 'var(--text-muted)', fontSize: 12 }} stroke="var(--border)" />
            <YAxis
              width={56}
              tick={{ fill: 'var(--text-muted)', fontSize: 12 }}
              stroke="var(--border)"
              tickFormatter={(value: number) => compact.format(value)}
            />
            <Tooltip
              contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8 }}
              formatter={(value, _name, item) => [
                `${formatValue(value as number | null, series.unit)} (${STATUS_LABELS[item.payload.status as keyof typeof STATUS_LABELS]})`,
                series.label,
              ]}
              labelFormatter={(label) => `Räkenskapsår ${label}`}
            />
            <Line
              type="monotone"
              dataKey="value"
              stroke="var(--chart-1)"
              strokeWidth={2}
              dot={{ r: 3, fill: 'var(--chart-1)' }}
              connectNulls={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
      {missingYears.length > 0 && <div className="small muted">Uppgift saknas för {missingYears.join(', ')}.</div>}
      {special.length > 0 && (
        <div className="small muted">
          {special.map((v) => `${v.fiscal_year}: ${STATUS_LABELS[v.display_status].toLowerCase()}`).join(' · ')}
        </div>
      )}
    </div>
  )
}
