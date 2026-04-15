import React, { useState } from 'react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
} from 'recharts'

function normalizedToColor(n) {
  if (n == null) return '#64748b'
  if (n >= 75) return '#D50000'
  if (n >= 55) return '#FF6D00'
  if (n >= 45) return '#FFD600'
  if (n >= 25) return '#76FF03'
  return '#00C853'
}

function normalizedToLabel(n) {
  if (n == null) return 'Unknown'
  if (n >= 75) return 'Extreme Fear'
  if (n >= 55) return 'Fear'
  if (n >= 45) return 'Neutral'
  if (n >= 25) return 'Greed'
  return 'Extreme Greed'
}

function CustomTooltipContent({ active, payload }) {
  if (!active || !payload?.length) return null
  const d = payload[0]?.payload
  if (!d) return null
  return (
    <div className="bg-slate-800 border border-slate-600 rounded-lg px-3 py-2.5 text-xs shadow-xl max-w-xs">
      <p className="text-slate-200 font-semibold mb-1">{d.name}</p>
      {d.description && (
        <p className="text-slate-400 mb-2 leading-relaxed">{d.description}</p>
      )}
      <div className="flex justify-between gap-4">
        <span className="text-slate-400">Value</span>
        <span className="text-slate-100 font-medium">{d.rawValue}</span>
      </div>
      <div className="flex justify-between gap-4">
        <span className="text-slate-400">Score</span>
        <span style={{ color: normalizedToColor(d.normalized) }} className="font-semibold">
          {Math.round(d.normalized)} — {normalizedToLabel(d.normalized)}
        </span>
      </div>
      {d.weight != null && (
        <div className="flex justify-between gap-4">
          <span className="text-slate-400">Weight</span>
          <span className="text-slate-100">{Math.round(d.weight * 100)}%</span>
        </div>
      )}
    </div>
  )
}

function ComponentRow({ component, index, isExpanded, onToggle }) {
  const color = normalizedToColor(component.normalized)
  const pct = Math.round(component.normalized ?? 50)

  return (
    <div className="border-b border-slate-700 last:border-0">
      <button
        className="w-full text-left py-3 px-1 flex items-center gap-3 hover:bg-slate-700/30 rounded-lg transition-colors group"
        onClick={() => onToggle(index)}
        aria-expanded={isExpanded}
      >
        {/* Rank number */}
        <span className="text-slate-600 text-xs w-4 shrink-0 text-right">{index + 1}</span>

        {/* Name */}
        <span className="text-slate-300 text-sm font-medium flex-1 text-left">{component.name}</span>

        {/* Score badge */}
        <span
          className="text-xs font-bold px-2 py-0.5 rounded-full shrink-0"
          style={{ backgroundColor: `${color}20`, color, border: `1px solid ${color}44` }}
        >
          {pct}
        </span>

        {/* Expand chevron */}
        <span
          className="text-slate-500 text-xs group-hover:text-slate-300 transition-colors shrink-0"
          style={{ transform: isExpanded ? 'rotate(180deg)' : 'rotate(0deg)', display: 'inline-block', transition: 'transform 0.2s ease' }}
        >
          ▾
        </span>
      </button>

      {/* Progress bar */}
      <div className="px-1 pb-2 -mt-1">
        <div className="flex items-center gap-2">
          <div className="flex-1 h-1.5 bg-slate-700 rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-700"
              style={{ width: `${pct}%`, backgroundColor: color }}
            />
          </div>
          <span className="text-[10px] text-slate-500 w-6 text-right">{pct}%</span>
        </div>
      </div>

      {/* Expanded details */}
      {isExpanded && (
        <div className="px-1 pb-3 bg-slate-900/40 rounded-lg mx-1 mb-2 mt-0.5 p-3">
          {component.description && (
            <p className="text-slate-400 text-xs leading-relaxed mb-2">{component.description}</p>
          )}
          <div className="grid grid-cols-3 gap-2 text-xs">
            <div>
              <div className="text-slate-500 mb-0.5">Raw Value</div>
              <div className="text-slate-200 font-medium">
                {typeof component.value === 'number'
                  ? component.value.toFixed(3)
                  : component.value ?? '—'}
              </div>
            </div>
            <div>
              <div className="text-slate-500 mb-0.5">Normalized</div>
              <div className="font-semibold" style={{ color }}>
                {pct} / 100
              </div>
            </div>
            <div>
              <div className="text-slate-500 mb-0.5">Signal</div>
              <div className="font-medium" style={{ color }}>
                {normalizedToLabel(component.normalized)}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

/**
 * @param {{ components?: Array, score?: number, label?: string }} props
 */
export default function FearGreedComponents({ components = [], score = null, label = '' }) {
  const [expandedIdx, setExpandedIdx] = useState(null)

  const handleToggle = (idx) => {
    setExpandedIdx((prev) => (prev === idx ? null : idx))
  }

  if (!components || components.length === 0) {
    return (
      <div className="bg-slate-800 border border-slate-700 rounded-xl p-6 text-center text-slate-500">
        No component data available
      </div>
    )
  }

  // Prepare bar chart data
  const chartData = components.map((c) => ({
    name: c.name?.split(' ').slice(0, 2).join(' ') || 'Unknown',
    fullName: c.name,
    normalized: Math.round(c.normalized ?? 50),
    rawValue: typeof c.value === 'number' ? c.value.toFixed(3) : (c.value ?? '—'),
    description: c.description,
    weight: c.weight,
  }))

  const overallColor = normalizedToColor(score)

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
      {/* Header */}
      <div className="flex items-start justify-between mb-5">
        <div>
          <h2 className="text-slate-100 font-semibold text-base">Fear & Greed Components</h2>
          <p className="text-slate-500 text-xs mt-0.5">
            {components.length} indicators · click a row to expand
          </p>
        </div>
        {score != null && (
          <div className="text-right">
            <div
              className="text-2xl font-bold"
              style={{ color: overallColor }}
            >
              {Math.round(score)}
            </div>
            <div className="text-xs text-slate-400">{label}</div>
          </div>
        )}
      </div>

      {/* Bar chart */}
      <div className="h-40 mb-5">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={chartData}
            margin={{ top: 4, right: 8, left: -20, bottom: 4 }}
            layout="vertical"
            barCategoryGap="20%"
          >
            <XAxis
              type="number"
              domain={[0, 100]}
              tickCount={6}
              tick={{ fill: '#64748b', fontSize: 10 }}
              tickLine={false}
              axisLine={{ stroke: '#334155' }}
            />
            <YAxis
              type="category"
              dataKey="name"
              width={90}
              tick={{ fill: '#94a3b8', fontSize: 10 }}
              tickLine={false}
              axisLine={false}
            />
            <Tooltip
              content={<CustomTooltipContent />}
              cursor={{ fill: 'rgba(255,255,255,0.04)' }}
            />
            <ReferenceLine x={50} stroke="#334155" strokeDasharray="4 4" />
            <Bar dataKey="normalized" radius={[0, 4, 4, 0]} maxBarSize={16}>
              {chartData.map((entry, i) => (
                <Cell key={`cell-${i}`} fill={normalizedToColor(entry.normalized)} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Score zones legend */}
      <div className="flex flex-wrap gap-x-4 gap-y-1 mb-5 text-[10px]">
        {[
          { range: '0–25', label: 'Extreme Greed', color: '#00C853' },
          { range: '25–45', label: 'Greed', color: '#76FF03' },
          { range: '45–55', label: 'Neutral', color: '#FFD600' },
          { range: '55–75', label: 'Fear', color: '#FF6D00' },
          { range: '75–100', label: 'Extreme Fear', color: '#D50000' },
        ].map((z) => (
          <span key={z.label} className="flex items-center gap-1">
            <span
              className="w-2 h-2 rounded-sm inline-block"
              style={{ backgroundColor: z.color }}
            />
            <span style={{ color: z.color }}>{z.range}</span>
            <span className="text-slate-500">{z.label}</span>
          </span>
        ))}
      </div>

      {/* Detailed rows */}
      <div>
        {components.map((comp, i) => (
          <ComponentRow
            key={comp.name || i}
            component={comp}
            index={i}
            isExpanded={expandedIdx === i}
            onToggle={handleToggle}
          />
        ))}
      </div>
    </div>
  )
}

