"""
Fear & Greed Index proxy data fetcher.

CNN publishes a proprietary Fear & Greed Index based on seven market signals.
Since that index isn't freely accessible via API, this module reimplements the
same seven components using free Yahoo Finance data:

  1. Market Momentum       — SPY price vs its 125-day moving average.
                             Above MA = greed; below = fear.
  2. Stock Price Strength  — 52-week high/low breadth proxy via SPY RSI (14-day).
                             High RSI = greed (overbought); low RSI = fear.
  3. Stock Price Breadth   — Advance/decline proxy using sector ETF breadth.
                             Most sectors up = greed; most down = fear.
  4. Put/Call Ratio        — Equity P/C ratio (^PCCE). Same as the put_call endpoint.
                             High ratio = fear; low = greed.
  5. Market Volatility     — VIX vs its 50-day moving average.
                             VIX above MA = fear; below = greed.
  6. Safe Haven Demand     — SPY 20-day return vs TLT 20-day return.
                             Stocks outperform bonds = greed; bonds outperform = fear.
  7. Junk Bond Demand      — HYG 20-day return vs LQD 20-day return.
                             High yield outperforms = greed (risk appetite is high).

Each component is normalized to 0–100 (0 = extreme greed, 100 = extreme fear)
and weighted equally (1/7 each) to produce an aggregate score.

Labels:
   0–25  = Extreme Greed
  25–45  = Greed
  45–55  = Neutral
  55–75  = Fear
  75–100 = Extreme Fear
"""

import logging
from datetime import date, timedelta
from typing import Optional, Tuple

import numpy as np
import pandas as pd
import yfinance as yf

import cache

logger = logging.getLogger(__name__)

CACHE_KEY = "fear_greed"
HISTORY_DAYS = 200  # need 125+ days for the MA calculation
COMPONENT_WEIGHT = round(1 / 7, 6)

# Tickers needed
SPY = "SPY"
TLT = "TLT"   # iShares 20+ Year Treasury Bond ETF (safe haven proxy)
HYG = "HYG"   # iShares High Yield Corporate Bond ETF (junk bonds)
LQD = "LQD"   # iShares Investment Grade Corporate Bond ETF
VIX = "^VIX"
PCCE = "^PCCE"

# Breadth sector ETFs (same set as sectors.py, minus XLRE/XLP/XLU to keep it simple)
BREADTH_ETFS = ["XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLU", "XLB", "XLRE", "XLC"]


def _score_label(score: float) -> str:
    """Convert a 0–100 aggregate score to a human-readable Fear & Greed label."""
    if score >= 75:
        return "Extreme Fear"
    if score >= 55:
        return "Fear"
    if score >= 45:
        return "Neutral"
    if score >= 25:
        return "Greed"
    return "Extreme Greed"


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    """Clamp *value* to the [lo, hi] range."""
    return max(lo, min(hi, value))


def _rsi(prices: pd.Series, period: int = 14) -> Optional[float]:
    """Compute the Relative Strength Index for the most recent bar.

    RSI measures momentum: values near 100 = overbought (greed),
    values near 0 = oversold (fear).

    Args:
        prices: Close price series, sorted oldest-first.
        period: Lookback period (default 14 days per Wilder's original spec).

    Returns:
        RSI value in [0, 100], or None if there isn't enough data.
    """
    prices = prices.dropna()
    if len(prices) < period + 1:
        return None

    delta = prices.diff().dropna()
    gains = delta.clip(lower=0)
    losses = -delta.clip(upper=0)

    avg_gain = gains.rolling(period).mean().iloc[-1]
    avg_loss = losses.rolling(period).mean().iloc[-1]

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(float(100.0 - 100.0 / (1 + rs)), 4)


def _pct_return(prices: pd.Series, days: int) -> Optional[float]:
    """Return the percentage change over the last *days* trading sessions.

    Args:
        prices: Close price series, sorted oldest-first.
        days: Number of trading bars to look back.

    Returns:
        Percentage change (e.g., 5.2 = +5.2%), or None if insufficient data.
    """
    prices = prices.dropna()
    if len(prices) < days + 1:
        return None
    old = prices.iloc[-(days + 1)]
    new = prices.iloc[-1]
    if old == 0:
        return None
    return round((new / old - 1) * 100.0, 4)


# ---------------------------------------------------------------------------
# Component calculations (each returns a (raw_value, normalized_score) tuple)
# ---------------------------------------------------------------------------

def _component_momentum(spy: pd.Series) -> Tuple[float, float]:
    """Component 1: Market Momentum — SPY vs its 125-day moving average.

    If SPY is above its 125-day MA, the market has been trending upward
    (greed). Below the MA indicates a downtrend (fear).

    Normalization:
      deviation = (SPY_price - MA125) / MA125 * 100  (percentage)
      ≥ +5%  → score 0   (Extreme Greed)
      ≤ -5%  → score 100 (Extreme Fear)
      Linear in between.
    """
    spy = spy.dropna()
    if len(spy) < 126:
        return 0.0, 50.0

    ma125 = spy.rolling(125).mean().iloc[-1]
    current = spy.iloc[-1]
    deviation = (current / ma125 - 1.0) * 100.0  # percentage deviation

    BOUND = 5.0
    norm = _clamp((deviation + BOUND) / (2 * BOUND) * 100.0)
    # Invert: positive deviation (above MA) = greed = LOW fear score
    return round(float(deviation), 4), round(100.0 - norm, 2)


def _component_strength(spy: pd.Series) -> Tuple[float, float]:
    """Component 2: Stock Price Strength — SPY RSI(14) as a breadth proxy.

    A high RSI means the market has been rising consistently (greed/overbought).
    A low RSI means consecutive down days (fear/oversold).

    Normalization:
      RSI is already 0–100 but its fear direction is reversed:
        RSI high → greed → LOW fear score
        RSI low  → fear  → HIGH fear score
    """
    rsi = _rsi(spy, period=14)
    if rsi is None:
        return 50.0, 50.0
    # Invert RSI: high RSI = greed = 0 fear; low RSI = fear = 100 fear
    return round(rsi, 4), round(100.0 - rsi, 2)


def _component_breadth(sector_closes: pd.DataFrame) -> Tuple[float, float]:
    """Component 3: Stock Price Breadth — advance/decline proxy via sector ETFs.

    Counts how many of the 11 sector ETFs are positive over the last 5 days.
    100% advancing = extreme greed; 0% advancing = extreme fear.

    Normalization:
      advancing_pct = (advancing_count / total) * 100
      advancing_pct maps directly to a greed signal, so we invert for fear score.
    """
    sector_closes = sector_closes.dropna(how="all")
    if sector_closes.empty or len(sector_closes) < 6:
        return 0.5, 50.0

    last_5 = sector_closes.tail(6)  # 6 rows = 5 daily changes
    changes = last_5.pct_change().iloc[1:]  # drop first NaN row
    five_day_sum = changes.sum(axis=0)
    advancing = int((five_day_sum > 0).sum())
    total = int(five_day_sum.notna().sum())

    if total == 0:
        return 0.0, 50.0

    adv_pct = advancing / total  # 0.0–1.0
    # High advance pct = greed = LOW fear score
    fear_score = round((1.0 - adv_pct) * 100.0, 2)
    return round(adv_pct, 4), fear_score


def _component_put_call(pcce: pd.Series) -> Tuple[float, float]:
    """Component 4: Put/Call ratio — same normalization as put_call.py.

    Ratio < 0.70 → score 0 (Extreme Greed)
    Ratio > 1.20 → score 100 (Extreme Fear)
    """
    pcce = pcce.dropna()
    if pcce.empty:
        return 0.85, 50.0

    value = float(pcce.iloc[-1])
    PC_LOW, PC_HIGH = 0.70, 1.20
    norm = _clamp((value - PC_LOW) / (PC_HIGH - PC_LOW) * 100.0)
    return round(value, 4), round(norm, 2)


def _component_volatility(vix: pd.Series) -> Tuple[float, float]:
    """Component 5: Market Volatility — VIX vs its 50-day moving average.

    When VIX is trading well above its 50-day MA, volatility is spiking
    (fear). When it's below, markets are unusually calm (greed).

    Normalization:
      deviation = (VIX - MA50) / MA50 * 100
      ≥ +30%  → score 100 (Extreme Fear — VIX has spiked far above average)
      ≤ -30%  → score 0   (Extreme Greed — VIX is depressed)
      Linear in between.
    """
    vix = vix.dropna()
    if len(vix) < 51:
        return 0.0, 50.0

    ma50 = vix.rolling(50).mean().iloc[-1]
    current = float(vix.iloc[-1])
    deviation = (current / ma50 - 1.0) * 100.0  # percentage above/below MA

    BOUND = 30.0
    norm = _clamp((deviation + BOUND) / (2 * BOUND) * 100.0)
    return round(deviation, 4), round(norm, 2)


def _component_safe_haven(spy: pd.Series, tlt: pd.Series) -> Tuple[float, float]:
    """Component 6: Safe Haven Demand — SPY vs TLT 20-day performance.

    When investors flee to bonds (TLT outperforms SPY), it signals fear.
    When stocks (SPY) outperform bonds, risk appetite is high (greed).

    Normalization:
      spread = SPY_20d_return - TLT_20d_return (percentage points)
      ≥ +10pp → score 0   (Extreme Greed — stocks crushing bonds)
      ≤ -10pp → score 100 (Extreme Fear  — bonds crushing stocks)
      Linear in between.
    """
    spy_ret = _pct_return(spy, 20)
    tlt_ret = _pct_return(tlt, 20)

    if spy_ret is None or tlt_ret is None:
        return 0.0, 50.0

    spread = spy_ret - tlt_ret
    BOUND = 10.0
    norm = _clamp((spread + BOUND) / (2 * BOUND) * 100.0)
    # Positive spread (stocks > bonds) = greed → LOW fear score
    return round(spread, 4), round(100.0 - norm, 2)


def _component_junk_bond(hyg: pd.Series, lqd: pd.Series) -> Tuple[float, float]:
    """Component 7: Junk Bond Demand — HYG vs LQD 20-day performance.

    When investors are comfortable buying high-yield (junk) bonds, they're
    accepting more risk — a sign of greed. When they only want investment-grade
    bonds, they're risk-averse (fear).

    Normalization:
      spread = HYG_20d_return - LQD_20d_return (percentage points)
      ≥ +3pp  → score 0   (Extreme Greed — junk outperforming IG)
      ≤ -3pp  → score 100 (Extreme Fear  — IG outperforming junk)
      Linear in between.
    """
    hyg_ret = _pct_return(hyg, 20)
    lqd_ret = _pct_return(lqd, 20)

    if hyg_ret is None or lqd_ret is None:
        return 0.0, 50.0

    spread = hyg_ret - lqd_ret
    BOUND = 3.0
    norm = _clamp((spread + BOUND) / (2 * BOUND) * 100.0)
    # Positive spread (junk > IG) = greed → LOW fear score
    return round(spread, 4), round(100.0 - norm, 2)


# ---------------------------------------------------------------------------
# Mock data
# ---------------------------------------------------------------------------

def _mock_data() -> dict:
    """Return plausible mock Fear & Greed data when live fetching is unavailable."""
    mock_score = 52.0

    components = [
        {
            "name": "Market Momentum",
            "value": 1.8,
            "normalized": 46.0,
            "weight": COMPONENT_WEIGHT,
            "description": "SPY vs 125-day MA — above average suggests greed",
        },
        {
            "name": "Stock Price Strength",
            "value": 54.2,
            "normalized": 45.8,
            "weight": COMPONENT_WEIGHT,
            "description": "SPY RSI(14) — high RSI = overbought = greed",
        },
        {
            "name": "Stock Price Breadth",
            "value": 0.55,
            "normalized": 45.0,
            "weight": COMPONENT_WEIGHT,
            "description": "Sector advance/decline breadth — most sectors rising = greed",
        },
        {
            "name": "Put/Call Ratio",
            "value": 0.85,
            "normalized": 30.0,
            "weight": COMPONENT_WEIGHT,
            "description": "CBOE equity put/call ratio — high ratio = fear",
        },
        {
            "name": "Market Volatility",
            "value": 5.2,
            "normalized": 58.7,
            "weight": COMPONENT_WEIGHT,
            "description": "VIX vs 50-day MA — VIX above average = fear",
        },
        {
            "name": "Safe Haven Demand",
            "value": 2.1,
            "normalized": 39.5,
            "weight": COMPONENT_WEIGHT,
            "description": "SPY vs TLT 20-day return — stocks outperform bonds = greed",
        },
        {
            "name": "Junk Bond Demand",
            "value": 0.8,
            "normalized": 63.3,
            "weight": COMPONENT_WEIGHT,
            "description": "HYG vs LQD 20-day return — junk outperforms IG = greed",
        },
    ]

    return {
        "score": mock_score,
        "label": _score_label(mock_score),
        "components": components,
        "data_source": "mock",
    }


# ---------------------------------------------------------------------------
# Public fetch interface
# ---------------------------------------------------------------------------

def fetch() -> dict:
    """Fetch the Fear & Greed proxy score, returning cached or mock data on failure.

    Downloads SPY, TLT, HYG, LQD, ^VIX, ^PCCE, and sector ETF price history
    in two bulk calls. Computes all seven components and combines them into
    an aggregate score.

    Returns:
        Dict matching the ``GET /api/fear-greed`` response schema.
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
        logger.error("Fear & Greed live fetch failed: %s", exc, exc_info=True)

    # 3. Stale cache fallback
    stale = cache.get_stale(CACHE_KEY)
    if stale is not None:
        logger.warning("Fear & Greed: serving stale cached data")
        return stale

    # 4. Last resort — mock data
    logger.warning("Fear & Greed: falling back to mock data")
    return _mock_data()


def _fetch_live() -> dict:
    """Download all required tickers and compute the seven Fear & Greed components.

    Raises:
        ValueError: If critical tickers (SPY, VIX) return no data.
        Exception: Propagated from yfinance on network/parsing errors.
    """
    period_start = (date.today() - timedelta(days=HISTORY_DAYS)).isoformat()
    period_end = (date.today() + timedelta(days=1)).isoformat()

    # --- Batch 1: Core tickers ---
    core_tickers = [SPY, TLT, HYG, LQD, VIX, PCCE]
    core_raw: pd.DataFrame = yf.download(
        core_tickers,
        start=period_start,
        end=period_end,
        interval="1d",
        progress=False,
        auto_adjust=True,
        threads=True,
    )

    if core_raw.empty:
        raise ValueError("yfinance returned empty DataFrame for core tickers")

    if isinstance(core_raw.columns, pd.MultiIndex):
        core_close: pd.DataFrame = core_raw["Close"]
    else:
        core_close = core_raw

    core_close.index = pd.to_datetime(core_close.index).normalize()

    def _get_series(ticker: str) -> pd.Series:
        if ticker in core_close.columns:
            return core_close[ticker].dropna()
        logger.warning("Ticker %s not in core download results", ticker)
        return pd.Series(dtype=float)

    spy_prices = _get_series(SPY)
    tlt_prices = _get_series(TLT)
    hyg_prices = _get_series(HYG)
    lqd_prices = _get_series(LQD)
    vix_prices = _get_series(VIX)
    pcce_prices = _get_series(PCCE)

    if spy_prices.empty:
        raise ValueError("SPY price series is empty — cannot compute Fear & Greed")

    # --- Batch 2: Sector ETFs (for breadth component) ---
    sector_raw: pd.DataFrame = yf.download(
        BREADTH_ETFS,
        start=period_start,
        end=period_end,
        interval="1d",
        progress=False,
        auto_adjust=True,
        threads=True,
    )

    if not sector_raw.empty:
        if isinstance(sector_raw.columns, pd.MultiIndex):
            sector_close: pd.DataFrame = sector_raw["Close"]
        else:
            sector_close = sector_raw
        sector_close.index = pd.to_datetime(sector_close.index).normalize()
    else:
        logger.warning("Sector ETF download empty; breadth component will use fallback")
        sector_close = pd.DataFrame()

    # --- Compute all seven components ---
    mom_val, mom_norm = _component_momentum(spy_prices)
    str_val, str_norm = _component_strength(spy_prices)
    brd_val, brd_norm = _component_breadth(sector_close)
    pc_val, pc_norm = _component_put_call(pcce_prices)
    vol_val, vol_norm = _component_volatility(vix_prices)
    sh_val, sh_norm = _component_safe_haven(spy_prices, tlt_prices)
    jb_val, jb_norm = _component_junk_bond(hyg_prices, lqd_prices)

    components = [
        {
            "name": "Market Momentum",
            "value": mom_val,
            "normalized": mom_norm,
            "weight": COMPONENT_WEIGHT,
            "description": "SPY vs 125-day MA — above average suggests greed",
        },
        {
            "name": "Stock Price Strength",
            "value": str_val,
            "normalized": str_norm,
            "weight": COMPONENT_WEIGHT,
            "description": "SPY RSI(14) — high RSI = overbought = greed",
        },
        {
            "name": "Stock Price Breadth",
            "value": brd_val,
            "normalized": brd_norm,
            "weight": COMPONENT_WEIGHT,
            "description": "Sector advance/decline breadth — most sectors rising = greed",
        },
        {
            "name": "Put/Call Ratio",
            "value": pc_val,
            "normalized": pc_norm,
            "weight": COMPONENT_WEIGHT,
            "description": "CBOE equity put/call ratio — high ratio = fear",
        },
        {
            "name": "Market Volatility",
            "value": vol_val,
            "normalized": vol_norm,
            "weight": COMPONENT_WEIGHT,
            "description": "VIX vs 50-day MA — VIX above average = fear",
        },
        {
            "name": "Safe Haven Demand",
            "value": sh_val,
            "normalized": sh_norm,
            "weight": COMPONENT_WEIGHT,
            "description": "SPY vs TLT 20-day return — stocks outperform bonds = greed",
        },
        {
            "name": "Junk Bond Demand",
            "value": jb_val,
            "normalized": jb_norm,
            "weight": COMPONENT_WEIGHT,
            "description": "HYG vs LQD 20-day return — junk outperforms IG = greed",
        },
    ]

    # Equal-weight aggregate score
    aggregate = round(
        sum(c["normalized"] for c in components) / len(components), 2
    )

    return {
        "score": aggregate,
        "label": _score_label(aggregate),
        "components": components,
        "data_source": "yfinance",
    }
