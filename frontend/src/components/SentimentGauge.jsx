import React, { useEffect, useRef, useState } from 'react'

// Score thresholds and colors
const ZONES = [
  { min: 0,  max: 25,  color: '#00C853', label: 'Extreme Greed' },
  { min: 25, max: 45,  color: '#76FF03', label: 'Greed' },
  { min: 45, max: 55,  color: '#FFD600', label: 'Neutral' },
  { min: 55, max: 75,  color: '#FF6D00', label: 'Fear' },
  { min: 75, max: 100, color: '#D50000', label: 'Extreme Fear' },
]

function getZoneColor(score) {
  const zone = ZONES.find((z) => score >= z.min && score <= z.max)
  return zone ? zone.color : '#FFD600'
}

function getZoneLabel(score) {
  const zone = ZONES.find((z) => score >= z.min && score <= z.max)
  return zone ? zone.label : 'Neutral'
}

// Convert a 0-100 score to an angle on the semicircle.
// The arc spans 180°: score=0 → -180° (left end), score=100 → 0° (right end).
// In SVG terms we map to radians where left=-π and right=0.
function scoreToAngle(score) {
  // angle in radians: 0 → -π, 100 → 0
  return Math.PI - (score / 100) * Math.PI
}

// Polar to Cartesian (cx, cy = center of full circle, r = radius)
function polarToCartesian(cx, cy, r, angleRad) {
  return {
    x: cx + r * Math.cos(Math.PI - angleRad),
    y: cy - r * Math.sin(angleRad),
  }
}

// Build an SVG arc path for a zone segment
function buildArcPath(cx, cy, outerR, innerR, startScore, endScore) {
  const startAngle = scoreToAngle(startScore)
  const endAngle = scoreToAngle(endScore)

  const outerStart = polarToCartesian(cx, cy, outerR, startAngle)
  const outerEnd = polarToCartesian(cx, cy, outerR, endAngle)
  const innerStart = polarToCartesian(cx, cy, innerR, startAngle)
  const innerEnd = polarToCartesian(cx, cy, innerR, endAngle)

  return [
    `M ${outerStart.x} ${outerStart.y}`,
    `A ${outerR} ${outerR} 0 0 1 ${outerEnd.x} ${outerEnd.y}`,
    `L ${innerEnd.x} ${innerEnd.y}`,
    `A ${innerR} ${innerR} 0 0 0 ${innerStart.x} ${innerStart.y}`,
    'Z',
  ].join(' ')
}

// Component label positions (tick marks along the outer arc at zone boundaries)
const TICK_SCORES = [0, 25, 45, 55, 75, 100]
const TICK_LABELS = ['Extreme\nGreed', 'Greed', 'Neutral', '', 'Fear', 'Extreme\nFear']

export default function SentimentGauge({ score = 50, label = 'Neutral', components = {} }) {
  const [animatedScore, setAnimatedScore] = useState(0)
  const animRef = useRef(null)
  const startTimeRef = useRef(null)
  const DURATION = 1200 // ms

  useEffect(() => {
    if (score == null) return
    const target = score
    startTimeRef.current = null

    function animate(ts) {
      if (!startTimeRef.current) startTimeRef.current = ts
      const elapsed = ts - startTimeRef.current
      const progress = Math.min(elapsed / DURATION, 1)
      // Cubic ease-out
      const eased = 1 - Math.pow(1 - progress, 3)
      setAnimatedScore(target * eased)
      if (progress < 1) {
        animRef.current = requestAnimationFrame(animate)
      }
    }

    cancelAnimationFrame(animRef.current)
    animRef.current = requestAnimationFrame(animate)
    return () => cancelAnimationFrame(animRef.current)
  }, [score])

  // SVG layout constants
  const W = 420
  const H = 260
  const cx = W / 2
  const cy = H - 40  // center of the circle (below bottom of SVG so only top half shows)
  const outerR = 160
  const innerR = 110
  const needleR = 145
  const tickR = outerR + 10
  const labelR = outerR + 36

  // Needle
  const needleAngle = scoreToAngle(animatedScore)
  const needleTip = polarToCartesian(cx, cy, needleR, needleAngle)
  // Two base points perpendicular to needle direction
  const baseAngle1 = needleAngle + Math.PI / 2
  const baseAngle2 = needleAngle - Math.PI / 2
  const base1 = polarToCartesian(cx, cy, 10, baseAngle1)
  const base2 = polarToCartesian(cx, cy, 10, baseAngle2)

  const scoreColor = getZoneColor(animatedScore)

  // Component contributions as small arc labels
  const componentEntries = components ? Object.entries(components) : []

  const COMPONENT_LABELS = {
    vix: 'VIX',
    put_call: 'P/C',
    sector_breadth: 'Sectors',
    fear_greed: 'F&G',
  }

  return (
    <div className="flex flex-col items-center">
      <svg
        width="100%"
        viewBox={`0 0 ${W} ${H}`}
        style={{ maxWidth: '480px', overflow: 'visible' }}
        aria-label={`Sentiment gauge showing ${Math.round(animatedScore)} — ${label}`}
      >
        {/* Background track arc */}
        <path
          d={buildArcPath(cx, cy, outerR, innerR, 0, 100)}
          fill="#1e293b"
          stroke="#334155"
          strokeWidth="1"
        />

        {/* Colored zone arcs */}
        {ZONES.map((zone) => (
          <path
            key={zone.label}
            d={buildArcPath(cx, cy, outerR, innerR, zone.min, zone.max)}
            fill={zone.color}
            opacity="0.85"
          />
        ))}

        {/* Zone separator lines */}
        {[25, 45, 55, 75].map((s) => {
          const angle = scoreToAngle(s)
          const p1 = polarToCartesian(cx, cy, innerR - 2, angle)
          const p2 = polarToCartesian(cx, cy, outerR + 2, angle)
          return (
            <line
              key={s}
              x1={p1.x} y1={p1.y}
              x2={p2.x} y2={p2.y}
              stroke="#0f172a"
              strokeWidth="2"
            />
          )
        })}

        {/* Tick marks and labels */}
        {TICK_SCORES.map((s, i) => {
          const angle = scoreToAngle(s)
          const t1 = polarToCartesian(cx, cy, outerR + 2, angle)
          const t2 = polarToCartesian(cx, cy, outerR + 8, angle)
          const lp = polarToCartesian(cx, cy, labelR, angle)
          const rawLabel = TICK_LABELS[i]
          if (!rawLabel) return null
          const lines = rawLabel.split('\n')
          return (
            <g key={s}>
              <line x1={t1.x} y1={t1.y} x2={t2.x} y2={t2.y} stroke="#64748b" strokeWidth="1.5" />
              {lines.map((ln, li) => (
                <text
                  key={li}
                  x={lp.x}
                  y={lp.y + li * 12}
                  textAnchor="middle"
                  dominantBaseline="middle"
                  fill="#64748b"
                  fontSize="9"
                  fontFamily="Inter, system-ui, sans-serif"
                >
                  {ln}
                </text>
              ))}
            </g>
          )
        })}

        {/* Component weight indicators (small dots on inner arc edge) */}
        {componentEntries.map(([key, comp]) => {
          if (!comp || comp.normalized == null) return null
          const angle = scoreToAngle(comp.normalized)
          const dotPos = polarToCartesian(cx, cy, innerR - 12, angle)
          const lblPos = polarToCartesian(cx, cy, innerR - 28, angle)
          return (
            <g key={key}>
              <circle
                cx={dotPos.x}
                cy={dotPos.y}
                r="4"
                fill={getZoneColor(comp.normalized)}
                opacity="0.9"
                stroke="#0f172a"
                strokeWidth="1"
              />
              <text
                x={lblPos.x}
                y={lblPos.y}
                textAnchor="middle"
                dominantBaseline="middle"
                fill="#94a3b8"
                fontSize="8"
                fontFamily="Inter, system-ui, sans-serif"
              >
                {COMPONENT_LABELS[key] || key}
              </text>
            </g>
          )
        })}

        {/* Center hub circle */}
        <circle cx={cx} cy={cy} r="14" fill="#0f172a" stroke="#334155" strokeWidth="2" />

        {/* Needle */}
        <polygon
          points={`${needleTip.x},${needleTip.y} ${base1.x},${base1.y} ${base2.x},${base2.y}`}
          fill="#f1f5f9"
          opacity="0.95"
          filter="url(#needleShadow)"
        />

        {/* Needle center cap */}
        <circle cx={cx} cy={cy} r="7" fill="#f1f5f9" />

        {/* Drop shadow filter for needle */}
        <defs>
          <filter id="needleShadow" x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="0" dy="2" stdDeviation="3" floodColor="#000" floodOpacity="0.5" />
          </filter>
          <filter id="glowFilter" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="4" result="coloredBlur" />
            <feMerge>
              <feMergeNode in="coloredBlur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* Score text */}
        <text
          x={cx}
          y={cy - 52}
          textAnchor="middle"
          fill={scoreColor}
          fontSize="42"
          fontWeight="700"
          fontFamily="Inter, system-ui, sans-serif"
          filter="url(#glowFilter)"
        >
          {Math.round(animatedScore)}
        </text>

        {/* Label text */}
        <text
          x={cx}
          y={cy - 26}
          textAnchor="middle"
          fill="#cbd5e1"
          fontSize="14"
          fontWeight="500"
          fontFamily="Inter, system-ui, sans-serif"
          letterSpacing="0.05em"
        >
          {label || getZoneLabel(animatedScore)}
        </text>
      </svg>

      {/* Component legend below gauge */}
      {componentEntries.length > 0 && (
        <div className="flex flex-wrap justify-center gap-3 mt-1 px-4">
          {componentEntries.map(([key, comp]) => {
            if (!comp) return null
            const pct = Math.round((comp.weight || 0) * 100)
            return (
              <div
                key={key}
                className="flex items-center gap-1.5 text-xs text-slate-400"
                title={`Weight: ${pct}% · Normalized: ${comp.normalized?.toFixed(1)}`}
              >
                <span
                  className="w-2.5 h-2.5 rounded-full inline-block"
                  style={{ backgroundColor: getZoneColor(comp.normalized || 50) }}
                />
                <span className="text-slate-300 font-medium">
                  {COMPONENT_LABELS[key] || key}
                </span>
                <span className="text-slate-500">{pct}%</span>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

/**
 * @param {{ score?: number, label?: string, components?: object }} props
 * score    - composite sentiment score 0–100
 * label    - e.g. "Greed", "Fear"
 * components - object keyed by component name with { value, normalized, weight }
 */
