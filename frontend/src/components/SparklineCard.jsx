import React, { useState } from 'react'
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'

const SIGNAL_CONFIG = {
  extreme_greed: { color: '#00C853', label: 'Extreme Greed', bg: 'rgba(0,200,83,0.12)' },
  greed:         { color: '#76FF03', label: 'Greed',         bg: 'rgba(118,255,3,0.10)' },
  neutral:       { color: '#FFD600', label: 'Neutral',       bg: 'rgba(255,214,0,0.10)' },
  fear:          { color: '#FF6D00', label: 'Fear',          bg: 'rgba(255,109,0,0.10)' },
  extreme_fear:  { color: '#D50000', label: 'Extreme Fear',  bg: 'rgba(213,0,0,0.12)' },
}

function getSignalConfig(signal) {
  if (!signal) return SIGNAL_CONFIG.neutral
  const key = signal.toLowerCase().replace(/\s+/g, '_').replace(/-/g, '_')
  return SIGNAL_CONFIG[key] || SIGNAL_CONFIG.neutral
}

function formatDate(dateStr) {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

function CustomTooltip({ active, payload, label, unit }) {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-xs shadow-xl">
      <p className="text-slate-400 mb-1">{formatDate(label)}</p>
      <p className="text-slate-100 font-semibold">
        {payload[0]?.value?.toFixed(2)}
        {unit ? <span className="text-slate-400 ml-1">{unit}</span> : null}
      </p>
    </div>
  )
}

function TrendArrow({ history }) {
  if (!history || history.length < 2) return null
  const first = history[0]?.value ?? history[0]?.normalized
  const last = history[history.length - 1]?.value ?? history[history.length - 1]?.normalized
  if (first == null || last == null) return null
  const up = last >= first
  return (
    <span
      className={up ? 'trend-up' : 'trend-down'}
      style={{ display: 'inline-block', color: up ? '#00C853' : '#D50000', fontSize: '1.1em' }}
      title={`30-day trend: ${up ? 'up' : 'down'} ${Math.abs(last - first).toFixed(2)}`}
    >
      {up ? '▲' : '▼'}
    </span>
  )
}

/**
 * @param {{ title: string, description?: string, current?: number, normalized?: number, signal?: string, history?: Array, unit?: string }} props
 */
export default function SparklineCard({
  title,
  description = '',
  current = null,
  normalized = null,
  signal = 'neutral',
  history = [],
  unit = '',
}) {
  const [showTooltip, setShowTooltip] = useState(false)
  const cfg = getSignalConfig(signal)

  // Prepare chart data (last 30 points of history)
  const chartData = (history || [])
    .slice(-30)
    .map((h) => ({ date: h.date, value: h.value ?? h.normalized }))

  const gradientId = `sparkGrad_${title?.replace(/\s+/g, '_')}`

  return (
    <div
      className="sentiment-card bg-slate-800 border border-slate-700 rounded-xl p-4 flex flex-col gap-3"
      style={{ borderTop: `3px solid ${cfg.color}` }}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          <h3 className="text-slate-100 font-semibold text-sm leading-tight">{title}</h3>
          {/* Info tooltip trigger */}
          <div className="tooltip-container">
            <button
              className="w-4 h-4 rounded-full bg-slate-700 text-slate-400 text-[10px] flex items-center justify-center hover:bg-slate-600 transition-colors"
              onMouseEnter={() => setShowTooltip(true)}
              onMouseLeave={() => setShowTooltip(false)}
              aria-label={`Info about ${title}`}
            >
              ?
            </button>
            {showTooltip && description && (
              <div className="tooltip-content" style={{ whiteSpace: 'normal', width: '200px', bottom: '130%' }}>
                {description}
              </div>
            )}
          </div>
        </div>
        {/* Signal badge */}
        <span
          className="text-[10px] font-semibold px-2 py-0.5 rounded-full shrink-0"
          style={{ backgroundColor: cfg.bg, color: cfg.color, border: `1px solid ${cfg.color}44` }}
        >
          {cfg.label}
        </span>
      </div>

      {/* Current value row */}
      <div className="flex items-baseline gap-2">
        <span className="text-2xl font-bold text-slate-100">
          {current != null ? Number(current).toFixed(current < 10 ? 2 : 1) : '—'}
        </span>
        {unit && <span className="text-slate-500 text-sm">{unit}</span>}
        <TrendArrow history={history} />
        {normalized != null && (
          <span className="text-slate-500 text-xs ml-auto">
            Score: <span className="text-slate-300">{Math.round(normalized)}</span>
          </span>
        )}
      </div>

      {/* Sparkline */}
      <div className="h-20 -mx-1">
        {chartData.length > 1 ? (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={chartData} margin={{ top: 4, right: 4, left: 4, bottom: 0 }}>
              <defs>
                <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={cfg.color} stopOpacity={0.35} />
                  <stop offset="95%" stopColor={cfg.color} stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <XAxis dataKey="date" hide />
              <YAxis hide domain={['auto', 'auto']} />
              <Tooltip
                content={<CustomTooltip unit={unit} />}
                cursor={{ stroke: cfg.color, strokeWidth: 1, strokeDasharray: '3 3' }}
              />
              <Area
                type="monotone"
                dataKey="value"
                stroke={cfg.color}
                strokeWidth={2}
                fill={`url(#${gradientId})`}
                dot={false}
                activeDot={{ r: 4, fill: cfg.color, stroke: '#0f172a', strokeWidth: 2 }}
              />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <div className="h-full flex items-center justify-center text-slate-600 text-xs">
            No history data
          </div>
        )}
      </div>

      {/* Footer: date range */}
      {chartData.length > 1 && (
        <div className="flex justify-between text-[10px] text-slate-600">
          <span>{formatDate(chartData[0]?.date)}</span>
          <span className="text-slate-500">30-day</span>
          <span>{formatDate(chartData[chartData.length - 1]?.date)}</span>
        </div>
      )}
    </div>
  )
}

