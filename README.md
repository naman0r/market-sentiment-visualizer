# Market Sentiment Visualizer

A real-time dashboard that aggregates public market data into a single **sentiment score** — a 0–100 number telling you whether the stock market is driven by **fear** (panic selling, defensive positioning) or **greed** (risk-taking, speculation). Think of it as a weather forecast for market psychology.

---

## Table of Contents

- [What Is Market Sentiment?](#what-is-market-sentiment)
- [How the Score Is Calculated](#how-the-score-is-calculated)
- [The Signals Explained](#the-signals-explained)
- [Architecture](#architecture)
- [Setup and Running Locally](#setup-and-running-locally)
- [Deployment](#deployment)
- [Data Sources and Limitations](#data-sources-and-limitations)

---

## What Is Market Sentiment?

Stock prices are driven by two forces: **fundamentals** (earnings, growth, interest rates) and **sentiment** (how nervous or confident investors feel *right now*). Even if a company's fundamentals are strong, a panic-driven market can push its stock down — and vice versa.

Market sentiment indicators measure the *emotional temperature* of the market:

| Score | Label | What It Means |
|-------|-------|---------------|
| 0–25 | Extreme Greed | Investors are piling in recklessly. Historically a warning sign — markets often pull back from here. |
| 25–45 | Greed | Risk appetite is high. Investors prefer stocks over bonds, cyclical sectors are outperforming. |
| 45–55 | Neutral | No strong directional bias. The market is balanced between buyers and sellers. |
| 55–75 | Fear | Investors are cautious. Money flows to safe assets (bonds, utilities). Volatility is rising. |
| 75–100 | Extreme Fear | Panic. Investors are selling indiscriminately. Historically a buying opportunity (contrarian signal). |

> **Warren Buffett's rule:** "Be fearful when others are greedy, and greedy when others are fearful." Extreme readings in either direction often signal market turning points.

---

## How the Score Is Calculated

Each signal is **normalized** to a 0–100 scale (0 = extreme greed, 100 = extreme fear), then combined using a weighted average:

```
Composite Score = (VIX × 25%) + (Put/Call Ratio × 20%) + (Sector Breadth × 20%) + (Fear & Greed Proxy × 35%)
```

The result is a single headline number updated every 15 minutes during market hours.

---

## The Signals Explained

### 1. VIX — The "Fear Index" (25% weight)

**What it is:** The CBOE Volatility Index measures how much the options market expects the S&P 500 to move over the next 30 days. Options traders pay more for protection when they're scared.

**How to read it:**
- VIX < 12: Markets are calm, complacency. Often seen at market peaks.
- VIX 12–20: Normal range.
- VIX 20–30: Elevated anxiety.
- VIX > 30: Fear/panic. The VIX hit ~80 during the 2008 financial crisis.

**Normalization:** `score = clamp((VIX - 12) / (40 - 12) × 100, 0, 100)`

**Data source:** CBOE via Yahoo Finance (`^VIX` ticker)

---

### 2. Put/Call Ratio (20% weight)

**What it is:** In options markets, a **put** is the right to sell (protection against a drop), and a **call** is the right to buy (bet on a rise). When traders are scared, they buy more puts. The put/call ratio is: `Total Put Volume ÷ Total Call Volume`.

**How to read it:**
- Ratio < 0.7: Lots of call buying → bullish sentiment → greed
- Ratio 0.7–1.0: Balanced
- Ratio > 1.0: Heavy put buying → defensive positioning → fear

**Normalization:** `score = clamp((ratio - 0.7) / (1.2 - 0.7) × 100, 0, 100)`

**Data source:** CBOE daily statistics (equity put/call `^PCCE` via Yahoo Finance as proxy)

---

### 3. Sector Rotation / Breadth (20% weight)

**What it is:** The stock market has 11 sectors. When investors are optimistic ("risk-on"), they buy **cyclical sectors** — companies whose earnings rise and fall with the economy. When scared ("risk-off"), they rotate into **defensive sectors** — companies that provide stable earnings regardless of economic conditions.

**Cyclical (risk-on) sectors:**
- **XLK** — Technology
- **XLY** — Consumer Discretionary (luxury spending)
- **XLF** — Financials (banks profit when economy grows)
- **XLI** — Industrials

**Defensive (risk-off) sectors:**
- **XLU** — Utilities (electricity bills don't stop in recessions)
- **XLP** — Consumer Staples (food, toothpaste — necessities)
- **XLRE** — Real Estate (dividend income)

**How it's scored:** We measure breadth — what percentage of sectors are rising. Then we weight defensive sectors as "fear signals" and cyclical sectors as "greed signals".

**Data source:** Yahoo Finance sector ETF prices

---

### 4. Fear & Greed Proxy (35% weight)

A 7-component composite inspired by CNN's Fear & Greed Index. Each component gets an equal 1/7 weight:

| Component | What It Measures | Fear Signal |
|-----------|-----------------|-------------|
| **Market Momentum** | SPY price vs its 125-day moving average | Price below MA = fear |
| **Stock Price Strength** | RSI overbought/oversold | RSI < 30 = fear |
| **Stock Price Breadth** | Cyclical vs defensive sector spread | Defensives winning = fear |
| **Put/Call Ratio** | Same as above | High ratio = fear |
| **Market Volatility** | VIX vs its 50-day moving average | VIX above MA = fear |
| **Safe Haven Demand** | SPY returns vs TLT (20yr Treasury bonds) | Bonds outperforming = fear |
| **Junk Bond Demand** | HYG (high yield) vs LQD (investment grade) | Spreads widening = fear |

> **Junk Bond Demand explained:** Companies with shaky finances issue "junk" (high-yield) bonds at high interest rates. When investors are confident, they happily buy these risky bonds for the extra yield. When fearful, they dump junk bonds and buy safe government bonds. The spread between junk and investment-grade yields is a real-time confidence barometer.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         Browser                              │
│                                                             │
│   ┌─────────────────────────────────────────────────────┐   │
│   │           React Frontend (Vite, port 3000)          │   │
│   │  ┌──────────┐ ┌──────────┐ ┌──────────────────────┐ │   │
│   │  │ Sentiment│ │Sparkline │ │   Sector Heatmap     │ │   │
│   │  │  Gauge   │ │  Cards   │ │   (11 ETFs)          │ │   │
│   │  └──────────┘ └──────────┘ └──────────────────────┘ │   │
│   └─────────────────────────────────────────────────────┘   │
│                            │ HTTP /api/*                     │
└────────────────────────────┼────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────┐
│              Python FastAPI Backend (port 8000)              │
│                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ File Cache  │  │  Rate Limit  │  │  Error Fallbacks    │  │
│  │ (.cache/)   │  │  15min TTL  │  │  (mock data)        │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
│                            │                                 │
│  ┌─────────────────────────▼───────────────────────────────┐ │
│  │              Data Fetchers                               │ │
│  │  vix.py │ put_call.py │ sectors.py │ fear_greed.py     │ │
│  └─────────────────────────┬───────────────────────────────┘ │
└────────────────────────────┼────────────────────────────────┘
                             │
          ┌──────────────────┼──────────────────┐
          │                  │                  │
   ┌──────▼──────┐  ┌────────▼────┐   ┌────────▼────┐
   │Yahoo Finance│  │    CBOE     │   │  Yahoo Fin. │
   │  (yfinance) │  │  (scraping) │   │ Sector ETFs │
   │  ^VIX, SPY  │  │  Put/Call   │   │ XLK,XLF...  │
   └─────────────┘  └─────────────┘   └─────────────┘
```

### Why a Backend?

Web browsers block direct API calls to most financial data endpoints due to **CORS** (Cross-Origin Resource Sharing) — a security policy that prevents websites from making requests to domains they weren't loaded from. The FastAPI backend acts as a **proxy**: it fetches data server-side where CORS doesn't apply, caches it, and serves it to the frontend.

### Caching Strategy

Market data has 15-minute delays on free tiers anyway, so we cache aggressively:
- **Market hours** (9:30am–4:00pm ET, Mon–Fri): Cache for 15 minutes
- **After hours / weekends**: Cache for 24 hours (data won't change)
- Cache stored as JSON files in `.cache/` directory (no Redis needed)

---

## Setup and Running Locally

### Prerequisites

- **Python 3.11+** — [python.org](https://python.org)
- **Node.js 18+** — [nodejs.org](https://nodejs.org)
- **Git** — [git-scm.com](https://git-scm.com)

### 1. Clone the Repository

```bash
git clone https://github.com/naman0r/order-book.git
cd order-book
```

### 2. Set Up the Backend

```bash
cd backend

# Create a virtual environment (keeps dependencies isolated)
python -m venv venv

# Activate it
# On Mac/Linux:
source venv/bin/activate
# On Windows:
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy environment variables
cp .env.example .env

# Start the backend server
uvicorn main:app --reload --port 8000
```

The backend will be running at **http://localhost:8000**.

You can verify it's working by visiting:
- http://localhost:8000/api/health
- http://localhost:8000/docs — Interactive API documentation (Swagger UI)

### 3. Set Up the Frontend

Open a **new terminal tab/window**:

```bash
cd frontend

# Install Node.js dependencies
npm install

# Copy environment variables
cp .env.example .env

# Start the development server
npm run dev
```

The frontend will be running at **http://localhost:3000** (or the port Vite assigns).

### 4. Open the App

Navigate to **http://localhost:3000** in your browser. You should see the Market Sentiment Dashboard.

> **Note:** The backend must be running for the frontend to display real data. If the backend is not running, you'll see loading errors in the UI.

### Running Both at Once (Optional)

If you have `concurrently` installed globally, you can run both from the root:

```bash
npm install -g concurrently
concurrently "cd backend && uvicorn main:app --reload --port 8000" "cd frontend && npm run dev"
```

---

## Deployment

### Frontend — Vercel (Free)

1. Push code to GitHub
2. Go to [vercel.com](https://vercel.com) → Import Project
3. Set root directory to `frontend`
4. Set environment variable: `VITE_API_URL=https://your-backend-url.railway.app`
5. Deploy

### Backend — Railway (Free Tier)

1. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub
2. Set root directory to `backend`
3. Set start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. Add environment variable: `PORT=8000`
5. Deploy

> **Important:** After deploying the backend, update the `VITE_API_URL` in your Vercel frontend deployment to point to the Railway backend URL.

---

## Data Sources and Limitations

### Free Tier Limitations

| Source | Delay | Limit |
|--------|-------|-------|
| Yahoo Finance (yfinance) | 15 min | ~2,000 requests/hour |
| CBOE Put/Call CSV | End-of-day | Daily update |

### Market Hours

Data is only meaningful during US market hours:
- **Pre-market:** 4:00am–9:30am ET (thin trading, less reliable)
- **Regular hours:** 9:30am–4:00pm ET (best data quality)
- **After hours:** 4:00pm–8:00pm ET

On **weekends and holidays**, markets are closed. The dashboard will show the most recent available data and indicate the market is closed.

### What This Is Not

This is an educational tool, not financial advice. The composite score is a simplified model and should not be used alone to make investment decisions. Past sentiment patterns do not guarantee future market performance.

---

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make your changes and commit: `git commit -m 'Add my feature'`
4. Push: `git push origin feature/my-feature`
5. Open a Pull Request

---

## License

MIT License — see [LICENSE](LICENSE) for details.
