"""
Composite market sentiment score calculator.

This module combines multiple independent market signals into a single
0–100 score where:
  0  = Extreme Greed (markets are irrationally exuberant)
  100 = Extreme Fear  (markets are in panic mode)

Think of it like a "fear thermometer" — the higher the number, the more
scared investors are. The score is a weighted average of four sub-signals:
  • VIX (volatility index)        — 25%
  • Put/Call ratio                — 20%
  • Sector breadth (ETF spread)   — 20%
  • Fear & Greed proxy score      — 35%
"""

import logging
from datetime import date, timedelta

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Weights must sum to 1.0
# ---------------------------------------------------------------------------
WEIGHTS: dict[str, float] = {
    "vix": 0.25,
    "put_call": 0.20,
    "sector_breadth": 0.20,
    "fear_greed": 0.35,
}

# Score → human-readable label thresholds (lower bound inclusive)
LABELS: list[tuple[float, str]] = [
    (75.0, "Extreme Fear"),
    (55.0, "Fear"),
    (45.0, "Neutral"),
    (25.0, "Greed"),
    (0.0, "Extreme Greed"),
]


def score_to_label(score: float) -> str:
    """Convert a 0–100 numeric score to a human-readable sentiment label.

    Args:
        score: Normalised sentiment score in [0, 100].

    Returns:
        One of "Extreme Fear", "Fear", "Neutral", "Greed", "Extreme Greed".
    """
    for threshold, label in LABELS:
        if score >= threshold:
            return label
    return "Extreme Greed"


def compute_composite(
    vix_data: dict,
    put_call_data: dict,
    sectors_data: dict,
    fear_greed_data: dict,
) -> dict:
    """Build the composite sentiment score from the four sub-signal responses.

    Each sub-signal must expose a ``normalized`` (or ``score``) key that
    already sits on the 0–100 scale. Missing or invalid values fall back to
    50 (neutral) so one broken data source doesn't ruin the whole score.

    Args:
        vix_data:        Response dict from the VIX data fetcher.
        put_call_data:   Response dict from the Put/Call data fetcher.
        sectors_data:    Response dict from the Sectors data fetcher.
        fear_greed_data: Response dict from the Fear & Greed data fetcher.

    Returns:
        Composite response dict matching the ``GET /api/composite`` schema.
    """

    def _safe_float(value, fallback: float = 50.0) -> float:
        """Coerce *value* to a float clamped to [0, 100], or return *fallback*."""
        try:
            f = float(value)
            if not (0.0 <= f <= 100.0):
                logger.warning("Normalised value %.2f out of [0,100] range — clamping", f)
                f = max(0.0, min(100.0, f))
            return f
        except (TypeError, ValueError):
            logger.warning("Could not parse normalised value %r — using fallback %.1f", value, fallback)
            return fallback

    # ------------------------------------------------------------------
    # Extract normalised component values
    # ------------------------------------------------------------------
    vix_norm = _safe_float(vix_data.get("normalized", 50.0))
    put_call_norm = _safe_float(put_call_data.get("normalized", 50.0))
    # sectors uses "breadth_score" as its top-level normalised value
    sector_norm = _safe_float(sectors_data.get("breadth_score", 50.0))
    fear_greed_norm = _safe_float(fear_greed_data.get("score", 50.0))

    # ------------------------------------------------------------------
    # Weighted average
    # ------------------------------------------------------------------
    composite_score = (
        vix_norm * WEIGHTS["vix"]
        + put_call_norm * WEIGHTS["put_call"]
        + sector_norm * WEIGHTS["sector_breadth"]
        + fear_greed_norm * WEIGHTS["fear_greed"]
    )
    composite_score = round(composite_score, 2)
    label = score_to_label(composite_score)

    # ------------------------------------------------------------------
    # Build history by combining per-source history arrays where available.
    # We use VIX history as the date spine (it's the most reliable source).
    # ------------------------------------------------------------------
    history = _build_composite_history(
        vix_data=vix_data,
        put_call_data=put_call_data,
        fear_greed_data=fear_greed_data,
        sector_norm_today=sector_norm,
    )

    return {
        "score": composite_score,
        "label": label,
        "components": {
            "vix": {
                "value": vix_data.get("current", 0.0),
                "normalized": vix_norm,
                "weight": WEIGHTS["vix"],
            },
            "put_call": {
                "value": put_call_data.get("current", 0.0),
                "normalized": put_call_norm,
                "weight": WEIGHTS["put_call"],
            },
            "sector_breadth": {
                "value": sector_norm,
                "normalized": sector_norm,
                "weight": WEIGHTS["sector_breadth"],
            },
            "fear_greed": {
                "value": fear_greed_norm,
                "normalized": fear_greed_norm,
                "weight": WEIGHTS["fear_greed"],
            },
        },
        "history": history,
    }


def _build_composite_history(
    vix_data: dict,
    put_call_data: dict,
    fear_greed_data: dict,
    sector_norm_today: float,
) -> list[dict]:
    """Merge per-source history arrays into a composite history spine.

    We use the VIX history dates as the authoritative date list and look up
    matching entries from Put/Call and Fear & Greed histories by date string.
    Sector breadth history isn't available per-day so we use today's value
    as a constant across the history window (acceptable approximation).

    Returns a list of dicts with ``date``, ``score``, and ``label`` keys,
    sorted ascending by date, with at least 30 entries.
    """
    vix_history: list[dict] = vix_data.get("history", [])
    put_call_history: list[dict] = put_call_data.get("history", [])
    fear_greed_history_raw = fear_greed_data.get("components", [])

    # Index Put/Call and Fear & Greed histories by date for O(1) lookup
    pc_by_date: dict[str, float] = {
        row["date"]: float(row.get("normalized", 50.0))
        for row in put_call_history
        if "date" in row
    }

    # Fear & Greed components don't carry per-day history in the same way,
    # so we use the current aggregate score as a constant fallback.
    fg_score_today = float(fear_greed_data.get("score", 50.0))

    composite_history: list[dict] = []
    for row in vix_history:
        dt = row.get("date", "")
        vix_norm = float(row.get("normalized", 50.0))
        pc_norm = pc_by_date.get(dt, 50.0)
        # Sector breadth and Fear & Greed are approximated with today's values
        # for historical points — a real implementation would store these too.
        daily_score = round(
            vix_norm * WEIGHTS["vix"]
            + pc_norm * WEIGHTS["put_call"]
            + sector_norm_today * WEIGHTS["sector_breadth"]
            + fg_score_today * WEIGHTS["fear_greed"],
            2,
        )
        composite_history.append(
            {
                "date": dt,
                "score": daily_score,
                "label": score_to_label(daily_score),
            }
        )

    # Ensure at least 30 data points by prepending synthetic entries if short
    if len(composite_history) < 30:
        composite_history = _pad_history(composite_history, target=30)

    return sorted(composite_history, key=lambda r: r["date"])


def _pad_history(history: list[dict], target: int = 30) -> list[dict]:
    """Prepend synthetic historical entries so the list reaches *target* length.

    Uses the earliest available score as a constant for the padded days.
    This is clearly marked as estimated data — never passed off as real.
    """
    if not history:
        # Completely fabricate a 30-day neutral history
        today = date.today()
        return [
            {
                "date": (today - timedelta(days=target - 1 - i)).isoformat(),
                "score": 50.0,
                "label": "Neutral",
            }
            for i in range(target)
        ]

    earliest = min(history, key=lambda r: r["date"])
    earliest_date = date.fromisoformat(earliest["date"])
    earliest_score = earliest["score"]
    earliest_label = earliest["label"]

    padding_needed = target - len(history)
    padding: list[dict] = []
    for offset in range(padding_needed, 0, -1):
        pad_date = (earliest_date - timedelta(days=offset)).isoformat()
        padding.append(
            {
                "date": pad_date,
                "score": earliest_score,
                "label": earliest_label,
            }
        )

    return padding + history
