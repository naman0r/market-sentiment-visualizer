import React, { useCallback, useEffect, useRef, useState } from 'react'
import {
  fetchComposite,
  fetchVix,
  fetchPutCall,
  fetchFearGreed,
  fetchSectors,
} from '../services/api.js'
import SentimentGauge from './SentimentGauge.jsx'
import SparklineCard from './SparklineCard.jsx'
import SectorHeatmap from './SectorHeatmap.jsx'
import FearGreedComponents from './FearGreedComponents.jsx'
import LoadingSpinner from './LoadingSpinner.jsx'

const REFRESH_INTERVAL_MS = 5 * 60 * 1000 // 5 minutes

// Check if the US equity market is currently closed.
// Market hours: Mon–Fri 09:30–16:00 ET
function isMarketClosed() {
  const now = new Date()
  // Convert to US/Eastern
  const etString = now.toLocaleString('en-US', { timeZone: 'America/New_York' })
  const et = new Date(etString)
  const day = et.getDay() // 0=Sun, 6=Sat
  const hours = et.getHours()
  const minutes = et.getMinutes()
  const timeInMinutes = hours * 60 + minutes

  if (day === 0 || day === 6) return true // weekend
  if (timeInMinutes < 9 * 60 + 30) return true  // before 09:30 ET
  if (timeInMinutes >= 16 * 60) return true      // at or after 16:00 ET
  return false
}

function formatTimestamp(date) {
  if (!date) return '—'
  return date.toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: true,
  })
}

function ErrorBanner({ message, onRetry }) {
  return (
    <div className="bg-red-900/30 border border-red-700/50 rounded-xl p-4 flex items-center justify-between gap-4">
      <div className="flex items-center gap-3">
        <span className="text-red-400 text-lg">⚠</span>
        <div>
          <p className="text-red-300 font-medium text-sm">Failed to load market data</p>
          <p className="text-red-400/70 text-xs mt-0.5">{message}</p>
        </div>
      </div>
      <button
        onClick={onRetry}
        className="shrink-0 px-3 py-1.5 bg-red-700/40 hover:bg-red-700/60 text-red-200 text-xs font-semibold rounded-lg transition-colors"
      >
        Retry
      </button>
    </div>
  )
}

function MarketClosedBanner() {
  return (
    <div className="market-closed-banner bg-amber-900/25 border border-amber-700/40 rounded-xl px-4 py-2.5 flex items-center gap-3">
      <span className="text-amber-400 text-base">🔔</span>
      <p className="text-amber-300 text-sm">
        <span className="font-semibold">Market Closed</span>
        <span className="text-amber-400/70 ml-2 text-xs">
          US equity markets are currently closed. Data shown may be from the last trading session.
        </span>
      </p>
    </div>
  )
}

function RefreshCountdown({ nextRefreshAt }) {
  const [secsLeft, setSecsLeft] = useState(null)

  useEffect(() => {
    if (!nextRefreshAt) return
    const tick = () => {
      const diff = Math.max(0, Math.round((nextRefreshAt - Date.now()) / 1000))
      setSecsLeft(diff)
    }
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [nextRefreshAt])

  if (secsLeft == null) return null
  const m = Math.floor(secsLeft / 60)
  const s = secsLeft % 60
  return (
    <span className="text-slate-600 text-xs tabular-nums">
      Next refresh: {m}:{String(s).padStart(2, '0')}
    </span>
  )
}

export default function Dashboard() {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [lastUpdated, setLastUpdated] = useState(null)
  const [nextRefreshAt, setNextRefreshAt] = useState(null)
  const [marketClosed, setMarketClosed] = useState(false)

  // Data state
  const [composite, setComposite] = useState(null)
  const [vix, setVix] = useState(null)
  const [putCall, setPutCall] = useState(null)
  const [fearGreed, setFearGreed] = useState(null)
  const [sectors, setSectors] = useState(null)

  const timerRef = useRef(null)

  const loadAll = useCallback(async () => {
    setError(null)
    try {
      const [compData, vixData, pcData, fgData, secData] = await Promise.all([
        fetchComposite(),
        fetchVix(),
        fetchPutCall(),
        fetchFearGreed(),
        fetchSectors(),
      ])
      setComposite(compData)
      setVix(vixData)
      setPutCall(pcData)
      setFearGreed(fgData)
      setSectors(secData)
      setLastUpdated(new Date())
      setNextRefreshAt(Date.now() + REFRESH_INTERVAL_MS)
      setMarketClosed(isMarketClosed())
    } catch (err) {
      setError(err?.message || 'Unknown error')
    } finally {
      setLoading(false)
    }
  }, [])

  // Initial load + auto-refresh
  useEffect(() => {
    loadAll()
    timerRef.current = setInterval(loadAll, REFRESH_INTERVAL_MS)
    return () => clearInterval(timerRef.current)
  }, [loadAll])

  if (loading) {
    return <LoadingSpinner message="Loading market data..." />
  }

  const compositeScore = composite?.score ?? 50
  const compositeLabel = composite?.label ?? 'Neutral'

  return (
    <div className="min-h-screen bg-slate-900 text-slate-100">
      {/* ── Top nav / header ── */}
      <header className="border-b border-slate-800 bg-slate-900/80 backdrop-blur sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-3 flex items-center justify-between gap-4">
          {/* Brand */}
          <div className="flex items-center gap-3">
            {/* Logo mark */}
            <div className="w-8 h-8 rounded-lg bg-blue-600/20 border border-blue-500/30 flex items-center justify-center shrink-0">
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                <path d="M2 12 L5 7 L8 10 L11 4 L14 8" stroke="#60a5fa" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" fill="none"/>
                <circle cx="14" cy="8" r="1.5" fill="#60a5fa"/>
              </svg>
            </div>
            <div>
              <h1 className="text-slate-100 font-bold text-base leading-tight tracking-tight">
                Market Sentiment Visualizer
              </h1>
              <p className="text-slate-500 text-[10px] leading-none mt-0.5">
                Real-time fear & greed analysis
              </p>
            </div>
          </div>

          {/* Status cluster */}
          <div className="flex items-center gap-4">
            <RefreshCountdown nextRefreshAt={nextRefreshAt} />
            {lastUpdated && (
              <div className="text-right hidden sm:block">
                <div className="text-[10px] text-slate-500 leading-none mb-0.5">Last updated</div>
                <div className="text-xs text-slate-400 tabular-nums font-medium">
                  {formatTimestamp(lastUpdated)}
                </div>
              </div>
            )}
            {/* Live indicator */}
            <div className="flex items-center gap-1.5">
              <span
                className="w-2 h-2 rounded-full bg-emerald-500"
                style={{ animation: 'pulse-glow 2s ease-in-out infinite' }}
              />
              <span className="text-emerald-400 text-xs font-medium hidden sm:inline">LIVE</span>
            </div>
            {/* Manual refresh button */}
            <button
              onClick={loadAll}
              className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-300 text-xs font-medium rounded-lg transition-colors"
              title="Refresh now"
            >
              ↺ Refresh
            </button>
          </div>
        </div>
      </header>

      {/* ── Main content ── */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-6 space-y-6">

        {/* Market closed banner */}
        {marketClosed && <MarketClosedBanner />}

        {/* Error banner */}
        {error && <ErrorBanner message={error} onRetry={loadAll} />}

        {/* ── Gauge section ── */}
        <section className="bg-slate-800 border border-slate-700 rounded-2xl p-6 flex flex-col items-center">
          <div className="flex flex-col items-center gap-1 mb-4 w-full">
            <h2 className="text-slate-400 text-xs font-semibold tracking-widest uppercase">
              Composite Sentiment Score
            </h2>
            <p className="text-slate-600 text-[11px]">
              Weighted average of VIX, Put/Call, Sector Breadth & Fear/Greed
            </p>
          </div>

          <SentimentGauge
            score={compositeScore}
            label={compositeLabel}
            components={composite?.components}
          />

          {/* History mini-stats */}
          {composite?.history && composite.history.length > 1 && (
            <div className="flex gap-6 mt-4 text-center">
              {[
                { label: '7D Avg', value: composite.history.slice(-7).reduce((a, h) => a + h.score, 0) / Math.min(7, composite.history.slice(-7).length) },
                { label: '30D Avg', value: composite.history.slice(-30).reduce((a, h) => a + h.score, 0) / Math.min(30, composite.history.slice(-30).length) },
                { label: 'All-time High', value: Math.max(...composite.history.map((h) => h.score)) },
                { label: 'All-time Low', value: Math.min(...composite.history.map((h) => h.score)) },
              ].map((stat) => (
                <div key={stat.label}>
                  <div className="text-slate-500 text-[10px] uppercase tracking-wide mb-0.5">{stat.label}</div>
                  <div className="text-slate-200 font-bold text-base">{stat.value.toFixed(1)}</div>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* ── Sparkline cards row ── */}
        <section>
          <h2 className="text-slate-400 text-xs font-semibold tracking-widest uppercase mb-3">
            Signal Components
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <SparklineCard
              title="VIX — Volatility Index"
              description="The CBOE Volatility Index measures expected 30-day market volatility. High VIX signals fear; low VIX signals greed. A VIX above 30 typically indicates Extreme Fear."
              current={vix?.current}
              normalized={vix?.normalized}
              signal={vix?.signal}
              history={vix?.history}
              unit=""
            />
            <SparklineCard
              title="Put/Call Ratio"
              description="The ratio of put options to call options traded on US exchanges. A high ratio (>1.0) means investors are buying more puts as protection, indicating fear. A low ratio signals greed."
              current={putCall?.current}
              normalized={putCall?.normalized}
              signal={putCall?.signal}
              history={putCall?.history}
              unit="ratio"
            />
            <SparklineCard
              title="Fear & Greed Index"
              description="CNN's composite Fear & Greed Index aggregates 7 indicators including market momentum, stock price breadth, safe haven demand, and junk bond spreads into a single 0-100 score."
              current={fearGreed?.score}
              normalized={fearGreed?.score}
              signal={fearGreed?.label}
              history={fearGreed?.history}
              unit=""
            />
          </div>
        </section>

        {/* ── Sector heatmap ── */}
        <section>
          <SectorHeatmap sectors={sectors?.sectors} />
        </section>

        {/* ── Fear & Greed breakdown ── */}
        <section>
          <FearGreedComponents
            components={fearGreed?.components}
            score={fearGreed?.score}
            label={fearGreed?.label}
          />
        </section>

        {/* ── Footer ── */}
        <footer className="border-t border-slate-800 pt-4 pb-6 flex flex-col sm:flex-row items-center justify-between gap-2 text-[11px] text-slate-600">
          <span>Market Sentiment Visualizer · Data refreshes every 5 minutes</span>
          <span>
            {lastUpdated
              ? `Last fetched: ${lastUpdated.toLocaleString('en-US', { dateStyle: 'medium', timeStyle: 'short' })}`
              : ''}
          </span>
          <span className="text-slate-700">
            Not financial advice. For informational purposes only.
          </span>
        </footer>
      </main>
    </div>
  )
}
