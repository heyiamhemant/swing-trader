# Swing Trader

Claude-powered swing trading signal generator for US stocks/ETFs on Vested Finance.

Claude (Opus) acts as the **full decision-maker** — it receives a complete data briefing
(technicals, fundamentals, macro regime) and returns specific stock picks with entry prices,
stop losses, targets, position sizes, and its reasoning.

## Setup

```bash
./launch.sh dashboard   # sets up venv, installs deps, opens dashboard
```

Or manually:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### Claude Access (pick one)

**Option A — Cursor Agent (preferred):**
Run commands from within the Cursor IDE. The system invokes Claude via Cursor's agent mode.

**Option B — Anthropic API:**
```bash
export ANTHROPIC_API_KEY="your_key_here"
```

**Option C — Manual:**
The system saves the prompt to `data/pending_prompt.txt`. Paste it into claude.ai,
save the JSON response to `data/claude_response.json`, then run with `--from-response`.

### Macro Data (optional)

For yield curve and VIX data from FRED:
```bash
export FRED_API_KEY="your_key_here"
```

## Usage

```bash
# Full market scan — Claude analyzes all stocks and picks a portfolio
python main.py scan

# Load a manually-saved Claude response
python main.py scan --from-response

# Quarterly rebalance — Claude reviews current positions + new data
python main.py rebalance

# Check open positions for exit signals
python main.py check

# View current portfolio
python main.py portfolio

# Log a trade entry
python main.py log-entry --ticker AAPL --price 185.50 --shares 0.54 --stop 170.60 --target 205.00

# Log a trade exit
python main.py log-exit --ticker AAPL --price 202.30 --reason target

# Quarterly performance review
python main.py review
python main.py review 2026Q2

# View full trade journal
python main.py journal

# View or update settings
python main.py config
python main.py config --capital 2000 --max-positions 8

# Generate and open the HTML dashboard
python main.py dashboard

# Run as a daemon (daily scans at market close)
python main.py daemon
```

## Dashboard

A self-contained HTML file (`data/dashboard.html`) is auto-generated after every scan,
trade entry, trade exit, and review. Double-click to open — no server needed.

Tabs: **Dashboard** | **Scan** | **Portfolio** | **Journal** | **Review** | **Settings**

The Settings tab lets you change capital, position limits, etc. It generates a CLI command
you paste into the terminal to apply changes.

## How It Works

```
  watchlist.yaml ──> Data Fetcher (yfinance + FRED)
                           │
                    ┌──────┴──────┐
                    ▼             ▼
              Technical      Fundamental
              Analysis       Analysis
              (RSI, MACD,    (P/E, ROE,
               EMA, ADX...)   FCF, growth...)
                    │             │
                    └──────┬──────┘
                           ▼
                    Macro Regime Detector
                    (SPY trend, VIX, yield curve)
                           │
                           ▼
                   ┌───────────────┐
                   │ DATA BRIEFING │ ◄── All scores, indicators, support/resistance
                   └───────┬───────┘
                           │
                           ▼
                   ┌───────────────┐
                   │   CLAUDE AI   │ ◄── Analyzes briefing, picks stocks,
                   │  (opus model) │     sets stops/targets, explains reasoning
                   └───────┬───────┘
                           │
                           ▼
                  CLI + HTML Dashboard
```

## Configuration

- `config/watchlist.yaml` — Stock/ETF universe (~450 tickers)
- `config/strategy_params.yaml` — Technical/fundamental thresholds, risk parameters
- `data/config.json` — User-editable overrides (capital, position limits)

## Data Storage

- `data/trades.csv` — Trade journal (entries, exits, P&L)
- `data/latest_decision.json` — Most recent Claude scan results
- `data/config.json` — User settings
- `data/dashboard.html` — Auto-generated dashboard (open in browser)
