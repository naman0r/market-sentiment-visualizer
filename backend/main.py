"""
Market Sentiment Visualizer — FastAPI backend.

This server aggregates multiple free market data signals into a unified
sentiment dashboard. All data comes from Yahoo Finance via the yfinance library,
with file-based caching to avoid hammering the data source.

Architecture overview:
  main.py            — FastAPI app, route definitions, CORS, error handling
  cache.py           — File-based JSON cache with market-hours-aware TTL
  composite_score.py — Weighted average of all sub-signals
  data_fetchers/
    vix.py           — CBOE Volatility Index (^VIX)
    put_call.py      — CBOE Equity Put/Call Ratio (^PCCE)
    sectors.py       — S&P 500 sector ETF performance (XLK, XLF, etc.)
    fear_greed.py    — 7-component Fear & Greed proxy (SPY, TLT, HYG, LQD, …)

Running the server:
  uvicorn main:app --reload --port 8000

Environment variables (see .env.example):
  CACHE_TTL — cache TTL in seconds (default 900 = 15 minutes)
  PORT      — server port (default 8000; used if you invoke via python main.py)
"""

import logging
import os
import sys
from datetime import datetime, timezone

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# ---------------------------------------------------------------------------
# Bootstrap: load .env, configure logging, add project root to sys.path
# ---------------------------------------------------------------------------

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Ensure the backend directory is on the path so sibling modules resolve.
# This matters when running from a different working directory.
_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

# ---------------------------------------------------------------------------
# Local imports (after sys.path fixup)
# ---------------------------------------------------------------------------

import cache  # noqa: E402 — must come after sys.path fixup
import composite_score  # noqa: E402
from data_fetchers import fear_greed, put_call, sectors, vix  # noqa: E402

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

CACHE_TTL: int = int(os.getenv("CACHE_TTL", "900"))

app = FastAPI(
    title="Market Sentiment Visualizer API",
    description=(
        "Aggregates free market data signals (VIX, Put/Call ratio, sector ETF "
        "performance, and a 7-component Fear & Greed proxy) into a unified "
        "sentiment dashboard. All data is sourced from Yahoo Finance."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ---------------------------------------------------------------------------
# CORS — allow the React dev server at localhost:3000 and any other origin.
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # permits all origins, including localhost:3000
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


def _utc_now_iso() -> str:
    """Return the current UTC timestamp as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _safe_fetch(fetcher_fn, cache_key: str, label: str) -> dict:
    """Call *fetcher_fn* with full error isolation.

    If the fetcher raises an unexpected exception (shouldn't happen — each
    fetcher is supposed to catch everything internally), we make a final
    attempt to serve stale cached data before returning a 503-like payload.

    Args:
        fetcher_fn:  Zero-argument callable that returns a data dict.
        cache_key:   Key to use for the last-resort stale cache lookup.
        label:       Human-readable name for this data source (used in logs).

    Returns:
        Response dict — never raises.
    """
    try:
        return fetcher_fn()
    except Exception as exc:  # noqa: BLE001
        logger.error("Unhandled error in %s fetcher: %s", label, exc, exc_info=True)

    # Last-ditch stale cache attempt
    stale = cache.get_stale(cache_key)
    if stale is not None:
        logger.warning("%s: serving stale cache after unhandled error", label)
        return stale

    # Give the caller a minimal valid response so the frontend doesn't crash
    return {
        "error": f"{label} data temporarily unavailable",
        "data_source": "error",
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get(
    "/api/health",
    summary="Health check",
    description="Returns a simple status payload confirming the server is running.",
    tags=["Utility"],
)
async def health_check() -> JSONResponse:
    """Return server health status with the current UTC timestamp.

    Frontend apps can poll this endpoint to verify the backend is alive.
    """
    return JSONResponse(
        content={
            "status": "ok",
            "timestamp": _utc_now_iso(),
        }
    )


@app.get(
    "/api/vix",
    summary="VIX Fear Index",
    description=(
        "Returns the CBOE Volatility Index (VIX), which measures how much "
        "the market expects the S&P 500 to move over the next 30 days. "
        "High VIX = high fear. Normalized to 0–100 (0 = Extreme Greed, "
        "100 = Extreme Fear) with 30 days of history."
    ),
    tags=["Market Signals"],
)
async def get_vix() -> JSONResponse:
    """Fetch and return VIX data.

    Data is cached for 15 minutes during market hours; the cache TTL extends
    to 24 hours when markets are closed (overnight, weekends).

    On failure, returns the most recent stale cached data or mock data.
    Response includes a ``data_source`` field: ``"yfinance"`` for live data,
    ``"mock"`` for fallback.
    """
    logger.info("GET /api/vix")
    data = _safe_fetch(vix.fetch, "vix", "VIX")
    return JSONResponse(content=data)


@app.get(
    "/api/put-call",
    summary="CBOE Put/Call Ratio",
    description=(
        "Returns the CBOE Equity Put/Call ratio (^PCCE). A high ratio means "
        "investors are buying many more put options (protection against falling "
        "prices) than calls — a sign of fear. A low ratio indicates complacency "
        "(greed). Normalized to 0–100 with 30 days of history."
    ),
    tags=["Market Signals"],
)
async def get_put_call() -> JSONResponse:
    """Fetch and return Put/Call ratio data.

    On failure, returns stale cache or mock data. Never crashes.
    """
    logger.info("GET /api/put-call")
    data = _safe_fetch(put_call.fetch, "put_call", "Put/Call")
    return JSONResponse(content=data)


@app.get(
    "/api/sectors",
    summary="S&P 500 Sector ETF Performance",
    description=(
        "Returns performance data for all 11 S&P 500 sector ETFs "
        "(XLK, XLF, XLE, XLV, XLI, XLY, XLP, XLU, XLB, XLRE, XLC). "
        "Includes 1-day, 5-day, and 30-day returns. Also computes a "
        "breadth_score (0–100) where high scores indicate fear-driven "
        "rotation into defensive sectors."
    ),
    tags=["Market Signals"],
)
async def get_sectors() -> JSONResponse:
    """Fetch and return sector ETF performance data.

    The breadth score looks at whether cyclical sectors (tech, financials,
    consumer discretionary) or defensive sectors (utilities, staples, real
    estate) are leading the market — a key indicator of risk appetite.

    On failure, returns stale cache or mock data. Never crashes.
    """
    logger.info("GET /api/sectors")
    data = _safe_fetch(sectors.fetch, "sectors", "Sectors")
    return JSONResponse(content=data)


@app.get(
    "/api/fear-greed",
    summary="Fear & Greed Index Proxy",
    description=(
        "Returns a 7-component Fear & Greed index proxy modelled on CNN's "
        "proprietary index. Components: Market Momentum (SPY vs 125-day MA), "
        "Stock Price Strength (SPY RSI), Stock Price Breadth (sector A/D), "
        "Put/Call Ratio, Market Volatility (VIX vs 50-day MA), Safe Haven "
        "Demand (SPY vs TLT), Junk Bond Demand (HYG vs LQD). Each component "
        "is normalized to 0–100 and averaged equally."
    ),
    tags=["Market Signals"],
)
async def get_fear_greed() -> JSONResponse:
    """Fetch and return the Fear & Greed proxy composite.

    This is the richest single endpoint — it downloads six tickers plus eleven
    sector ETFs to build the seven components. The result is cached aggressively
    to avoid slow responses.

    On failure, returns stale cache or mock data. Never crashes.
    """
    logger.info("GET /api/fear-greed")
    data = _safe_fetch(fear_greed.fetch, "fear_greed", "Fear & Greed")
    return JSONResponse(content=data)


@app.get(
    "/api/composite",
    summary="Composite Sentiment Score",
    description=(
        "Combines all four sub-signals into a single weighted sentiment score. "
        "Weights: VIX (25%), Put/Call (20%), Sector Breadth (20%), "
        "Fear & Greed (35%). Score ranges from 0 (Extreme Greed) to "
        "100 (Extreme Fear). Includes 30 days of composite history."
    ),
    tags=["Composite"],
)
async def get_composite() -> JSONResponse:
    """Fetch all sub-signals and compute the composite sentiment score.

    This endpoint calls all four underlying fetchers (which each check their
    own caches) and then merges them via composite_score.compute_composite().
    It caches its own result separately to avoid re-merging on every request.

    On failure at any sub-signal, the composite falls back to 50 (neutral)
    for that component, ensuring the overall score is always returned.
    """
    logger.info("GET /api/composite")

    # Check composite-level cache first
    cached = cache.get("composite")
    if cached is not None:
        return JSONResponse(content=cached)

    # Fetch all four sub-signals (each has its own internal cache + fallback)
    vix_data = _safe_fetch(vix.fetch, "vix", "VIX")
    put_call_data = _safe_fetch(put_call.fetch, "put_call", "Put/Call")
    sectors_data = _safe_fetch(sectors.fetch, "sectors", "Sectors")
    fear_greed_data = _safe_fetch(fear_greed.fetch, "fear_greed", "Fear & Greed")

    try:
        result = composite_score.compute_composite(
            vix_data=vix_data,
            put_call_data=put_call_data,
            sectors_data=sectors_data,
            fear_greed_data=fear_greed_data,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Composite score computation failed: %s", exc, exc_info=True)
        # Fall back to stale composite cache or a neutral placeholder
        stale = cache.get_stale("composite")
        if stale is not None:
            logger.warning("Composite: serving stale cache after computation error")
            return JSONResponse(content=stale)
        # Return a clearly-marked error payload that still has valid structure
        return JSONResponse(
            status_code=500,
            content={
                "score": 50.0,
                "label": "Neutral",
                "error": "Composite score temporarily unavailable",
                "components": {},
                "history": [],
            },
        )

    cache.set("composite", result, ttl=CACHE_TTL)
    return JSONResponse(content=result)


# ---------------------------------------------------------------------------
# 404 / generic exception handlers
# ---------------------------------------------------------------------------


@app.exception_handler(404)
async def not_found_handler(request, exc):  # noqa: ANN001
    """Return a JSON 404 instead of HTML."""
    return JSONResponse(
        status_code=404,
        content={
            "error": "Endpoint not found",
            "path": str(request.url.path),
            "available_endpoints": [
                "/api/health",
                "/api/vix",
                "/api/put-call",
                "/api/sectors",
                "/api/fear-greed",
                "/api/composite",
            ],
        },
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request, exc):  # noqa: ANN001
    """Catch-all handler — log the error and return a JSON 500.

    In a production system you'd also send an alert here. For this app we
    just log it and keep serving so the frontend never sees an empty page.
    """
    logger.error(
        "Unhandled exception on %s %s: %s",
        request.method,
        request.url.path,
        exc,
        exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)},
    )


# ---------------------------------------------------------------------------
# Entrypoint (python main.py)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    logger.info("Starting Market Sentiment Visualizer backend on port %d", port)
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=False,  # set True for development
        log_level="info",
    )
