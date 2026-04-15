"""
Data fetchers for the Market Sentiment Visualizer.

Each module in this package is responsible for one market signal:
  - vix        : CBOE Volatility Index — measures market fear via options pricing
  - put_call   : CBOE Put/Call ratio — sentiment from options traders
  - sectors    : S&P 500 sector ETF performance — shows rotation into/out of risk
  - fear_greed : Multi-component Fear & Greed proxy — CNN-style composite index

All fetchers follow the same contract:
  1. Check the shared file cache first.
  2. Attempt to fetch live data from yfinance (or another free source).
  3. On any failure, return stale cached data if available, else return mock data.
  4. Never raise — always return a valid response dict.
"""
