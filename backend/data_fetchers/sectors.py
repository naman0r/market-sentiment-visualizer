"""
S&P 500 Sector ETF performance data fetcher.

The 11 S&P 500 sector ETFs (Select Sector SPDRs) track distinct slices of the
economy. Monitoring which sectors are gaining or losing tells us a lot about
investor risk appetite:

  Cyclical sectors (risk-on / greed signals when they outperform):
    XLK  — Technology
    XLF  — Financials
    XLY  — Consumer Discretionary (luxury spending, autos, restaurants)
    XLI  — Industrials
    XLB  — Materials
    XLC  — Communication Services (Meta, Alphabet, Netflix)

  Defensive sectors (risk-off / fear signals when they outperform):
    XLU  — Utilities (stable dividends, bond-like)
    XLP  — Consumer Staples (food, beverages, household products)
    XLRE — Real Estate (dividend income, rate-sensitive)

  Mixed / ambiguous:
    XLE  — Energy (commodity-driven, can act independently)
    XLV  — Health Care (defensive but also growth)

Breadth score normalization (0–100 fear scale):
  We look at 5-day return for each sector, classify cyclical outperformance as
  "greed" and defensive outperformance as "fear", then average to a 0–100 score.
  Higher score = more fear.
"""

import logging
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yfinance as yf

import cache

logger = logging.getLogger(__name__)

CACHE_KEY = "sectors"
HISTORY_DAYS = 45  # calendar days — enough for ~30 trading days

# fmt: off
SECTOR_ETFS: List[Tuple[str, str, str]] = [
    # (ETF ticker, display name, category)
    ("XLK",  "Technology",             "cyclical"),
    ("XLF",  "Financials",             "cyclical"),
    ("XLE",  "Energy",                 "mixed"),
    ("XLV",  "Health Care",            "defensive"),
    ("XLI",  "Industrials",            "cyclical"),
    ("XLY",  "Consumer Discretionary", "cyclical"),
    ("XLP",  "Consumer Staples",       "defensive"),
    ("XLU",  "Utilities",              "defensive"),
    ("XLB",  "Materials",              "cyclical"),
    ("XLRE", "Real Estate",            "defensive"),
    ("XLC",  "Communication Services", "cyclical"),
]
# fmt: on

# Cyclical ETFs: outperformance → greed (low fear score)
CYCLICAL_ETFS = {row[0] for row in SECTOR_ETFS if row[2] == "cyclical"}
# Defensive ETFs: outperformance → fear (high fear score)
DEFENSIVE_ETFS = {row[0] for row in SECTOR_ETFS if row[2] == "defensive"}


def _signal_from_score(score: float) -> str:
    """Map a normalized 0–100 score to a sentiment signal label."""
    if score <= 25:
        return "extreme_greed"
    if score <= 45:
        return "greed"
    if score <= 55:
        return "neutral"
    if score <= 75:
        return "fear"
    return "extreme_fear"


def _normalize_return(ret: float, category: str) -> float:
    """Convert a 5-day percentage return to a 0–100 fear contribution.

    Cyclical outperformance (positive returns) → low fear (greed).
    Defensive outperformance (positive returns) → high fear.
    Mixed sectors → treat as neutral contribution (50).

    We use ±5% as the extreme bounds; beyond that we clamp.

    Args:
        ret: Percentage return (e.g., 2.5 for +2.5%).
        category: "cyclical", "defensive", or "mixed".

    Returns:
        Fear contribution in [0, 100].
    """
    if category == "mixed":
        return 50.0

    BOUND = 5.0  # ±5% is considered extreme
    clamped = max(-BOUND, min(BOUND, ret))
    # Map [-5, 5] → [0, 100]
    normalized = (clamped + BOUND) / (2 * BOUND) * 100.0

    if category == "cyclical":
        # Cyclical outperformance (positive ret) = greed = LOW fear score
        return round(100.0 - normalized, 2)
    else:
        # Defensive outperformance (positive ret) = fear = HIGH fear score
        return round(normalized, 2)


def _compute_return(prices: pd.Series, days: int) -> Optional[float]:
    """Compute a percentage return over *days* trading days.

    Args:
        prices: Time-ordered close price series.
        days: Number of trading periods to look back.

    Returns:
        Percentage change as a float (e.g., 2.5 = +2.5%), or None if
        there aren't enough data points.
    """
    prices = prices.dropna()
    if len(prices) < days + 1:
        return None
    old_price = prices.iloc[-(days + 1)]
    new_price = prices.iloc[-1]
    if old_price == 0:
        return None
    return round((new_price / old_price - 1) * 100.0, 4)


def _mock_sector(ticker: str, name: str, category: str) -> dict:
    """Build a plausible mock sector entry."""
    rng = np.random.default_rng(abs(hash(ticker)) % (2 ** 32))

    if category == "cyclical":
        # Lean slightly toward positive (greed scenario)
        change_1d = round(float(rng.normal(0.3, 0.8)), 4)
        change_5d = round(float(rng.normal(0.8, 1.5)), 4)
        change_30d = round(float(rng.normal(2.5, 4.0)), 4)
    elif category == "defensive":
        change_1d = round(float(rng.normal(-0.1, 0.5)), 4)
        change_5d = round(float(rng.normal(-0.3, 1.0)), 4)
        change_30d = round(float(rng.normal(0.5, 2.5)), 4)
    else:
        change_1d = round(float(rng.normal(0.0, 1.0)), 4)
        change_5d = round(float(rng.normal(0.5, 2.0)), 4)
        change_30d = round(float(rng.normal(1.0, 5.0)), 4)

    norm = _normalize_return(change_5d, category)
    return {
        "name": name,
        "etf": ticker,
        "change_1d": change_1d,
        "change_5d": change_5d,
        "change_30d": change_30d,
        "normalized": norm,
        "signal": _signal_from_score(norm),
    }


def _mock_data() -> dict:
    """Return plausible mock sector data when live fetching is unavailable."""
    sectors = [
        _mock_sector(ticker, name, cat)
        for ticker, name, cat in SECTOR_ETFS
    ]
    norms = [s["normalized"] for s in sectors if s["normalized"] is not None]
    breadth_score = round(float(np.mean(norms)), 2) if norms else 50.0

    return {
        "sectors": sectors,
        "breadth_score": breadth_score,
        "data_source": "mock",
    }


def fetch() -> dict:
    """Fetch sector ETF performance data, returning cached or mock data on failure.

    Downloads price history for all 11 sector ETFs simultaneously using
    yfinance's bulk download feature (one HTTP request). Computes 1-day,
    5-day, and 30-day returns for each, then derives a breadth score.

    Returns:
        Dict matching the ``GET /api/sectors`` response schema.
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
        logger.error("Sectors live fetch failed: %s", exc, exc_info=True)

    # 3. Stale cache fallback
    stale = cache.get_stale(CACHE_KEY)
    if stale is not None:
        logger.warning("Sectors: serving stale cached data")
        return stale

    # 4. Last resort — mock data
    logger.warning("Sectors: falling back to mock data")
    return _mock_data()


def _fetch_live() -> dict:
    """Download sector ETF data from Yahoo Finance and build the response.

    Uses yfinance bulk download (one request for all tickers) for efficiency.

    Raises:
        ValueError: If no usable data is returned.
        Exception: Propagated from yfinance on network/parsing errors.
    """
    tickers = [row[0] for row in SECTOR_ETFS]
    period_start = (date.today() - timedelta(days=HISTORY_DAYS)).isoformat()
    period_end = (date.today() + timedelta(days=1)).isoformat()

    # Bulk download — returns a MultiIndex DataFrame (metric × ticker)
    raw: pd.DataFrame = yf.download(
        tickers,
        start=period_start,
        end=period_end,
        interval="1d",
        progress=False,
        auto_adjust=True,
        threads=True,
    )

    if raw.empty:
        raise ValueError("yfinance bulk download returned empty DataFrame for sector ETFs")

    # Extract the Close price sub-frame; handle both MultiIndex and flat cases
    if isinstance(raw.columns, pd.MultiIndex):
        close_df: pd.DataFrame = raw["Close"]
    else:
        close_df = raw  # Single-ticker case (shouldn't happen for 11 tickers)

    close_df.index = pd.to_datetime(close_df.index).normalize()

    # Build per-sector results
    sector_info: Dict[str, Tuple[str, str]] = {
        row[0]: (row[1], row[2]) for row in SECTOR_ETFS
    }

    sector_results = []
    normalized_values = []

    for ticker in tickers:
        name, category = sector_info[ticker]

        if ticker not in close_df.columns:
            logger.warning("Sector ETF %s not found in download results", ticker)
            mock = _mock_sector(ticker, name, category)
            sector_results.append(mock)
            normalized_values.append(mock["normalized"])
            continue

        prices: pd.Series = close_df[ticker].dropna()

        if len(prices) < 2:
            logger.warning("Insufficient price data for %s", ticker)
            mock = _mock_sector(ticker, name, category)
            sector_results.append(mock)
            normalized_values.append(mock["normalized"])
            continue

        change_1d = _compute_return(prices, 1)
        change_5d = _compute_return(prices, 5)
        change_30d = _compute_return(prices, 30)

        # Use 5-day return for normalization; fall back to 1-day if unavailable
        ret_for_norm = change_5d if change_5d is not None else (change_1d or 0.0)
        norm = _normalize_return(ret_for_norm, category)
        normalized_values.append(norm)

        sector_results.append({
            "name": name,
            "etf": ticker,
            "change_1d": change_1d,
            "change_5d": change_5d,
            "change_30d": change_30d,
            "normalized": norm,
            "signal": _signal_from_score(norm),
        })

    if not sector_results:
        raise ValueError("No sector results could be built from downloaded data")

    breadth_score = round(float(np.mean(normalized_values)), 2) if normalized_values else 50.0

    return {
        "sectors": sector_results,
        "breadth_score": breadth_score,
        "data_source": "yfinance",
    }
