"""
CBOE Put/Call Ratio data fetcher.

The Put/Call ratio measures the volume of put options (bets that prices fall)
relative to call options (bets that prices rise). It's a classic contrarian
sentiment indicator:

  - Ratio < 0.7 : Extreme greed — traders are buying many more calls than puts,
                  suggesting over-confidence. Contrarians see this as a warning.
  - Ratio 0.7–1.0 : Normal range, mild optimism.
  - Ratio 1.0–1.2 : Elevated caution — more put buying than usual.
  - Ratio > 1.2 : Extreme fear — panic put buying, often a contrarian buy signal.

We use the CBOE Equity Put/Call ratio (^PCCE) from Yahoo Finance as a proxy
for the total CBOE Put/Call ratio. The equity-only ratio tends to be a cleaner
sentiment signal because it excludes index-level hedges by institutions.

Normalization to 0–100 (fear scale):
  Ratio ≤ 0.70 → score = 0   (Extreme Greed)
  Ratio ≥ 1.20 → score = 100 (Extreme Fear)
  Linear interpolation in between.
"""

import logging
from datetime import date, timedelta

import numpy as np
import pandas as pd
import yfinance as yf

import cache

logger = logging.getLogger(__name__)

CACHE_KEY = "put_call"
PCCE_TICKER = "^PCCE"   # CBOE Equity-Only Put/Call Ratio
HISTORY_DAYS = 45        # calendar days to request (covers ~30 trading days)
PC_LOW = 0.70            # ratio at or below → score 0 (Extreme Greed)
PC_HIGH = 1.20           # ratio at or above → score 100 (Extreme Fear)


def normalize_put_call(value: float) -> float:
    """Convert a raw Put/Call ratio to a 0–100 fear score.

    Args:
        value: Raw Put/Call ratio (e.g. 0.85).

    Returns:
        Fear score in [0, 100] where 0 = extreme greed, 100 = extreme fear.
    """
    clamped = max(PC_LOW, min(PC_HIGH, float(value)))
    return round((clamped - PC_LOW) / (PC_HIGH - PC_LOW) * 100.0, 2)


def _signal_from_score(score: float) -> str:
    """Map a normalized score to a sentiment signal label."""
    if score <= 25:
        return "extreme_greed"
    if score <= 45:
        return "greed"
    if score <= 55:
        return "neutral"
    if score <= 75:
        return "fear"
    return "extreme_fear"


def _mock_data() -> dict:
    """Return plausible mock Put/Call data when live fetching is unavailable.

    Uses a neutral ratio of 0.85 with gentle oscillation across 30 days so
    charts don't appear completely flat.
    """
    mock_pc = 0.85
    mock_norm = normalize_put_call(mock_pc)
    today = date.today()

    history = []
    for i in range(30):
        day = today - timedelta(days=29 - i)
        delta = 0.05 * np.sin(i / 4.5)
        val = round(mock_pc + delta, 4)
        val = max(PC_LOW - 0.1, val)  # keep it realistic
        norm = normalize_put_call(val)
        history.append({"date": day.isoformat(), "value": val, "normalized": norm})

    return {
        "current": mock_pc,
        "normalized": mock_norm,
        "signal": _signal_from_score(mock_norm),
        "history": history,
        "data_source": "mock",
    }


def fetch() -> dict:
    """Fetch Put/Call ratio data, returning cached or mock data on failure.

    Checks the file cache first (15-minute TTL during market hours, 24-hour TTL
    when markets are closed). Falls back to stale cache, then mock data.

    The CBOE Equity Put/Call ratio (^PCCE) is fetched via yfinance. Note that
    Yahoo Finance sometimes has gaps in this series — if data is sparse, the
    fetcher pads with the last known value.

    Returns:
        Dict matching the ``GET /api/put-call`` response schema.
    """
    # 1. Try fresh cache
    cached = cache.get(CACHE_KEY)
    if cached is not None:
        return cached

    # 2. Attempt live fetch
    try:
        data = _fetch_live()
        cache.set(CACHE_KEY, data)
        return data
    except Exception as exc:  # noqa: BLE001
        logger.error("Put/Call live fetch failed: %s", exc, exc_info=True)

    # 3. Stale cache fallback
    stale = cache.get_stale(CACHE_KEY)
    if stale is not None:
        logger.warning("Put/Call: serving stale cached data")
        return stale

    # 4. Last resort — mock data
    logger.warning("Put/Call: falling back to mock data")
    return _mock_data()


def _fetch_live() -> dict:
    """Download Put/Call ratio from Yahoo Finance via the ^PCCE ticker.

    ^PCCE is the CBOE Equity Put/Call Ratio. It's published daily after the
    market closes. Yahoo Finance carries historical values, though the series
    can have gaps on days with low options volume.

    Raises:
        ValueError: If yfinance returns empty or unusable data.
        Exception: Propagated from yfinance on network/parsing errors.
    """
    ticker = yf.Ticker(PCCE_TICKER)
    period_start = (date.today() - timedelta(days=HISTORY_DAYS)).isoformat()
    period_end = (date.today() + timedelta(days=1)).isoformat()

    hist: pd.DataFrame = ticker.history(start=period_start, end=period_end, interval="1d")

    if hist.empty:
        raise ValueError(f"yfinance returned empty DataFrame for {PCCE_TICKER}")

    # Normalise index to plain dates
    hist.index = pd.to_datetime(hist.index).normalize()

    close_series: pd.Series = hist["Close"].dropna()
    if close_series.empty:
        raise ValueError(f"No valid Close prices for {PCCE_TICKER}")

    # Take the most recent 30 trading-day observations
    close_series = close_series.tail(30)

    history_rows = []
    for ts, val in close_series.items():
        day_str = ts.strftime("%Y-%m-%d")
        ratio = round(float(val), 4)
        norm = normalize_put_call(ratio)
        history_rows.append({"date": day_str, "value": ratio, "normalized": norm})

    if not history_rows:
        raise ValueError("No valid history rows built for Put/Call")

    # Pad to 30 rows if yfinance returned fewer (fill-forward the earliest value)
    if len(history_rows) < 30:
        earliest = history_rows[0]
        earliest_date = date.fromisoformat(earliest["date"])
        needed = 30 - len(history_rows)
        padding = []
        for offset in range(needed, 0, -1):
            pad_date = (earliest_date - timedelta(days=offset)).isoformat()
            padding.append({
                "date": pad_date,
                "value": earliest["value"],
                "normalized": earliest["normalized"],
            })
        history_rows = padding + history_rows

    current_val = history_rows[-1]["value"]
    current_norm = normalize_put_call(current_val)

    return {
        "current": current_val,
        "normalized": current_norm,
        "signal": _signal_from_score(current_norm),
        "history": history_rows,
        "data_source": "yfinance",
    }
