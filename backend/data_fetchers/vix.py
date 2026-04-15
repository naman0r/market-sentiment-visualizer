"""
VIX (CBOE Volatility Index) data fetcher.

The VIX measures how much the market expects the S&P 500 to move over the
next 30 days, derived from options pricing. It's often called the "fear index":
  - VIX < 12 : Extreme complacency / greed — investors aren't buying protection
  - VIX 12–20: Normal, calm market conditions
  - VIX 20–30: Elevated uncertainty or moderate fear
  - VIX > 30 : Significant fear / panic; options are very expensive
  - VIX > 40 : Extreme fear or crisis conditions (seen in 2008, 2020 COVID crash)

Normalization to 0–100 (fear scale):
  VIX ≤ 12  → score = 0   (Extreme Greed)
  VIX ≥ 40  → score = 100 (Extreme Fear)
  Linear interpolation in between.
"""

import logging
from datetime import date, timedelta

import numpy as np
import pandas as pd
import yfinance as yf

import cache

logger = logging.getLogger(__name__)

CACHE_KEY = "vix"
VIX_TICKER = "^VIX"
HISTORY_DAYS = 45  # fetch extra to guarantee 30 trading days
VIX_LOW = 12.0     # VIX at or below this → score 0 (Extreme Greed)
VIX_HIGH = 40.0    # VIX at or above this → score 100 (Extreme Fear)


def normalize_vix(value: float) -> float:
    """Convert a raw VIX value to a 0–100 fear score.

    Args:
        value: Raw VIX level (typically 10–80).

    Returns:
        Fear score in [0, 100] where 0 = extreme greed, 100 = extreme fear.
    """
    clamped = max(VIX_LOW, min(VIX_HIGH, float(value)))
    return round((clamped - VIX_LOW) / (VIX_HIGH - VIX_LOW) * 100.0, 2)


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
    """Return plausible mock VIX data when live fetching is unavailable.

    The mock constructs 30 days of synthetic history around a neutral VIX of ~18
    with small random-ish variation so charts don't look completely flat.
    """
    mock_vix = 18.5
    mock_norm = normalize_vix(mock_vix)
    today = date.today()

    history = []
    for i in range(30):
        day = today - timedelta(days=29 - i)
        # Add a gentle sine wave to make the chart interesting
        delta = 2.0 * np.sin(i / 5.0)
        val = round(mock_vix + delta, 2)
        norm = normalize_vix(val)
        history.append({"date": day.isoformat(), "value": val, "normalized": norm})

    return {
        "current": mock_vix,
        "normalized": mock_norm,
        "signal": _signal_from_score(mock_norm),
        "history": history,
        "data_source": "mock",
    }


def fetch() -> dict:
    """Fetch VIX data, returning cached or mock data on failure.

    Checks the file cache first (15-minute TTL during market hours, 24-hour TTL
    when markets are closed). Falls back to stale cache, then mock data.

    Returns:
        Dict matching the ``GET /api/vix`` response schema.
    """
    # 1. Try fresh cache
    cached = cache.get(CACHE_KEY)
    if cached is not None:
        return cached

    # 2. Attempt live fetch from yfinance
    try:
        data = _fetch_live()
        cache.set(CACHE_KEY, data)
        return data
    except Exception as exc:  # noqa: BLE001
        logger.error("VIX live fetch failed: %s", exc, exc_info=True)

    # 3. Stale cache fallback
    stale = cache.get_stale(CACHE_KEY)
    if stale is not None:
        logger.warning("VIX: serving stale cached data")
        return stale

    # 4. Last resort — mock data
    logger.warning("VIX: falling back to mock data")
    return _mock_data()


def _fetch_live() -> dict:
    """Download VIX data from Yahoo Finance via yfinance.

    Raises:
        Exception: Propagated from yfinance on any download failure.
    """
    ticker = yf.Ticker(VIX_TICKER)
    # Fetch enough calendar days to cover ~30 trading days (markets closed ~30% of days)
    period_start = (date.today() - timedelta(days=HISTORY_DAYS)).isoformat()
    period_end = (date.today() + timedelta(days=1)).isoformat()

    hist: pd.DataFrame = ticker.history(start=period_start, end=period_end, interval="1d")

    if hist.empty:
        raise ValueError("yfinance returned empty DataFrame for ^VIX")

    # Normalise the index to plain date strings
    hist.index = pd.to_datetime(hist.index).normalize()

    # Build history list (most recent 30 trading days)
    close_series = hist["Close"].dropna().tail(30)
    history_rows = []
    for ts, val in close_series.items():
        day_str = ts.strftime("%Y-%m-%d")
        norm = normalize_vix(float(val))
        history_rows.append({"date": day_str, "value": round(float(val), 2), "normalized": norm})

    if not history_rows:
        raise ValueError("No valid close prices in VIX history")

    current = history_rows[-1]["value"]
    norm = normalize_vix(current)

    return {
        "current": current,
        "normalized": norm,
        "signal": _signal_from_score(norm),
        "history": history_rows,
        "data_source": "yfinance",
    }
