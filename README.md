# Swing Trader

Claude-powered swing trading signal generator for US stocks/ETFs on Vested Finance.

**One interface** — a local web dashboard where you can run scans, log trades,
close positions, change settings, and review performance. All from the browser.

## Quick Start

```bash
./launch.sh          # opens http://localhost:5050
./launch.sh 8080     # custom port
```

Or manually:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python server.py
```

### Claude Access (pick one)

**Option A — Cursor Agent (preferred):**
Run from within the Cursor IDE. The system invokes Claude via Cursor's agent mode.

**Option B — Anthropic API:**
```bash
export ANTHROPIC_API_KEY="your_key_here"
```

**Option C — Manual:**
The system saves the prompt to `data/pending_prompt.txt`. Paste it into claude.ai,
save the JSON response to `data/claude_response.json`, then click "Load Saved Response" in the dashboard.

### Macro Data

```bash
export FRED_API_KEY="your_key_here"
```

## Dashboard

Open `http://localhost:5050` after running `./launch.sh`. Everything is done from here:

| Tab | What it does |
|---|---|
| **Dashboard** | Capital, deployed, cash, P&L, regime, open positions |
| **Scan** | Run full market scan, see Claude's picks, one-click log trades |
| **Portfolio** | Open positions with "Close" buttons |
| **Journal** | All trades (open + closed), log new entries, delete trades |
| **Review** | Win rate, avg R:R, P&L breakdown |
| **Settings** | Edit capital, max positions, sector cap, brokerage fee — saved instantly |

## How It Works

```
  watchlist.yaml ──> Data Fetcher (yfinance + FRED)
                           │
                    ┌──────┴──────┐
                    ▼             ▼
              Technical      Fundamental
              Analysis       Analysis
                    │             │
                    └──────┬──────┘
                           ▼
                    Macro Regime Detector
                           │
                           ▼
                   ┌───────────────┐
                   │ DATA BRIEFING │
                   └───────┬───────┘
                           │
                           ▼
                   ┌───────────────┐
                   │   CLAUDE AI   │
                   │  (opus model) │
                   └───────┬───────┘
                           │
                           ▼
                   HTML Dashboard ◄──── localhost:5050
```

## CLI (still works)

```bash
python main.py scan
python main.py log-entry --ticker AAPL --price 185.50 --shares 0.54 --stop 170.60 --target 205.00
python main.py log-exit --ticker AAPL --price 202.30 --reason target
python main.py config --capital 2000
python main.py portfolio
python main.py journal
python main.py review
```

## Configuration

- `config/watchlist.yaml` — Stock/ETF universe (~450 tickers)
- `config/strategy_params.yaml` — Technical/fundamental thresholds, risk parameters
- `data/config.json` — User settings (capital, position limits)

## Data Storage

- `data/trades.csv` — Trade journal
- `data/latest_decision.json` — Most recent Claude scan
- `data/config.json` — User settings
