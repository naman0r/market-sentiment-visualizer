import React, { useState } from 'react'

const DEFENSIVE_ETFS = new Set(['XLU', 'XLP', 'XLRE'])
const CYCLICAL_ETFS = new Set(['XLK', 'XLY', 'XLF'])

// Interpolate between two hex colors by t ∈ [0, 1]
function lerpColor(hex1, hex2, t) {
  const parse = (h) => [
    parseInt(h.slice(1, 3), 16),
    parseInt(h.slice(3, 5), 16),
    parseInt(h.slice(5, 7), 16),
  ]
  const [r1, g1, b1] = parse(hex1)
  const [r2, g2, b2] = parse(hex2)
  const r = Math.round(r1 + (r2 - r1) * t)
  const g = Math.round(g1 + (g2 - g1) * t)
  const b = Math.round(b1 + (b2 - b1) * t)
  return `rgb(${r},${g},${b})`
}

// Map a percentage change to a cell background color.
// 0% → neutral slate, ≥+3% → bright green, ≤-3% → bright red
function changeToColor(pct) {
  const NEUTRAL = '#1e293b'
  const GREEN   = '#00C853'
  const RED     = '#D50000'
  const CLAMP = 3 // percent at which we hit full saturation

  if (pct == null) return NEUTRAL
  if (pct >= 0) {
    const t = Math.min(pct / CLAMP, 1)
    return lerpColor(NEUTRAL, GREEN, t)
  } else {
    const t = Math.min(Math.abs(pct) / CLAMP, 1)
    return lerpColor(NEUTRAL, RED, t)
  }
}

// Determine text color for readability on the cell background
function changeToTextColor(pct) {
  if (pct == null) return '#94a3b8'
  const t = Math.min(Math.abs(pct) / 3, 1)
  return t > 0.4 ? '#f1f5f9' : '#cbd5e1'
}

const PERIOD_KEYS = {
  '1D': 'change_1d',
  '5D': 'change_5d',
  '30D': 'change_30d',
}

// Shield SVG icon (defensive)
function ShieldIcon() {
  return (
    <svg width="10" height="11" viewBox="0 0 10 11" fill="none" aria-hidden="true">
      <path
        d="M5 1L1 2.5V5.5C1 7.8 2.8 9.9 5 10.5C7.2 9.9 9 7.8 9 5.5V2.5L5 1Z"
        fill="currentColor"
        opacity="0.8"
      />
    </svg>
  )
}

// Lightning SVG icon (cyclical)
function LightningIcon() {
  return (
    <svg width="9" height="12" viewBox="0 0 9 12" fill="none" aria-hidden="true">
      <path d="M5.5 1L1 6.5H4.5L3.5 11L8 5.5H4.5L5.5 1Z" fill="currentColor" opacity="0.9" />
    </svg>
  )
}

function SectorCell({ sector, period }) {
  const [hovered, setHovered] = useState(false)
  const changeKey = PERIOD_KEYS[period]
  const pct = sector[changeKey]
  const bg = changeToColor(pct)
  const textColor = changeToTextColor(pct)
  const isDefensive = DEFENSIVE_ETFS.has(sector.etf)
  const isCyclical = CYCLICAL_ETFS.has(sector.etf)

  return (
    <div
      className="heatmap-cell relative rounded-lg p-3 cursor-default select-none"
      style={{ backgroundColor: bg, color: textColor, minHeight: '80px' }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      title={`${sector.name} (${sector.etf})\n1D: ${sector.change_1d?.toFixed(2)}%\n5D: ${sector.change_5d?.toFixed(2)}%\n30D: ${sector.change_30d?.toFixed(2)}%`}
    >
      {/* Icon badge */}
      {(isDefensive || isCyclical) && (
        <span
          className="absolute top-1.5 right-1.5"
          style={{ color: isDefensive ? '#94a3b8' : '#fbbf24' }}
          title={isDefensive ? 'Defensive sector' : 'Cyclical sector'}
        >
          {isDefensive ? <ShieldIcon /> : <LightningIcon />}
        </span>
      )}

      {/* ETF ticker */}
      <div className="font-bold text-base leading-none mb-1 tracking-wide">
        {sector.etf}
      </div>

      {/* Sector name */}
      <div
        className="text-[10px] leading-tight mb-2 opacity-80 overflow-hidden"
        style={{ maxWidth: '90%' }}
      >
        {sector.name}
      </div>

      {/* Change */}
      <div className="font-semibold text-sm">
        {pct != null ? (
          <>
            {pct >= 0 ? '+' : ''}
            {pct.toFixed(2)}%
          </>
        ) : (
          '—'
        )}
      </div>

      {/* Hover: show all periods */}
      {hovered && (
        <div
          className="absolute inset-0 rounded-lg flex flex-col justify-center items-start p-3 gap-0.5 z-10"
          style={{ backgroundColor: '#1e293b', border: '1px solid #334155' }}
        >
          <div className="font-bold text-slate-100 text-sm">{sector.etf}</div>
          <div className="text-slate-400 text-[10px] mb-1">{sector.name}</div>
          {Object.entries(PERIOD_KEYS).map(([p, k]) => (
            <div key={p} className="flex justify-between w-full text-xs">
              <span className="text-slate-400">{p}</span>
              <span
                style={{
                  color:
                    sector[k] > 0
                      ? '#00C853'
                      : sector[k] < 0
                      ? '#D50000'
                      : '#94a3b8',
                  fontWeight: 600,
                }}
              >
                {sector[k] != null
                  ? `${sector[k] >= 0 ? '+' : ''}${sector[k].toFixed(2)}%`
                  : '—'}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

/**
 * @param {{ sectors?: Array<{name:string, etf:string, change_1d:number, change_5d:number, change_30d:number, normalized:number, signal:string}> }} props
 */
export default function SectorHeatmap({ sectors = [] }) {
  const [activePeriod, setActivePeriod] = useState('1D')

  if (!sectors || sectors.length === 0) {
    return (
      <div className="bg-slate-800 border border-slate-700 rounded-xl p-6 text-center text-slate-500">
        No sector data available
      </div>
    )
  }

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-slate-100 font-semibold text-base">Sector Performance</h2>
          <p className="text-slate-500 text-xs mt-0.5">
            11 SPDR sector ETFs · hover cell for all periods
          </p>
        </div>

        {/* Period tabs */}
        <div className="flex bg-slate-900 rounded-lg p-0.5 gap-0.5">
          {Object.keys(PERIOD_KEYS).map((p) => (
            <button
              key={p}
              onClick={() => setActivePeriod(p)}
              className={`px-3 py-1.5 rounded-md text-xs font-semibold transition-colors ${
                activePeriod === p
                  ? 'bg-slate-700 text-slate-100'
                  : 'text-slate-500 hover:text-slate-300'
              }`}
            >
              {p}
            </button>
          ))}
        </div>
      </div>

      {/* Legend */}
      <div className="flex items-center gap-4 mb-4 text-[10px] text-slate-500">
        <div className="flex items-center gap-1">
          <span className="w-8 h-2 rounded-sm inline-block" style={{ background: 'linear-gradient(to right, #D50000, #1e293b, #00C853)' }} />
          <span>−3% → 0 → +3%</span>
        </div>
        <div className="flex items-center gap-1" style={{ color: '#94a3b8' }}>
          <ShieldIcon />
          <span className="ml-1">Defensive</span>
        </div>
        <div className="flex items-center gap-1" style={{ color: '#fbbf24' }}>
          <LightningIcon />
          <span className="ml-1">Cyclical</span>
        </div>
      </div>

      {/* Grid */}
      <div
        className="grid gap-2"
        style={{
          gridTemplateColumns: 'repeat(auto-fill, minmax(110px, 1fr))',
        }}
      >
        {sectors.map((sector) => (
          <SectorCell key={sector.etf} sector={sector} period={activePeriod} />
        ))}
      </div>
    </div>
  )
}

