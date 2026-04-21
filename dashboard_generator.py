"""
Generates a single self-contained HTML dashboard from CSV/JSON data files.

Reads:
  - data/trades.csv
  - data/latest_decision.json
  - data/config.json

Writes:
  - data/dashboard.html
"""

import csv
import json
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"


def _read_trades() -> list[dict]:
    path = DATA_DIR / "trades.csv"
    if not path.exists():
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def _read_json(filename: str) -> dict | list:
    path = DATA_DIR / filename
    if not path.exists():
        return {} if filename.endswith(".json") else []
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, ValueError):
        return {}


def _compute_stats(trades: list[dict], config: dict) -> dict:
    capital = config.get("capital", 1000)
    open_trades = [t for t in trades if not t.get("exit_date")]
    closed_trades = [t for t in trades if t.get("exit_date")]

    deployed = sum(float(t.get("position_usd", 0)) for t in open_trades)
    cash = capital - deployed

    total_pnl = sum(float(t.get("pnl", 0)) for t in closed_trades if t.get("pnl"))
    winners = [t for t in closed_trades if float(t.get("pnl", 0)) > 0]
    win_rate = (len(winners) / len(closed_trades) * 100) if closed_trades else 0

    return {
        "capital": capital,
        "deployed": round(deployed, 2),
        "cash": round(cash, 2),
        "open_count": len(open_trades),
        "closed_count": len(closed_trades),
        "total_pnl": round(total_pnl, 2),
        "win_rate": round(win_rate, 1),
    }


def generate_dashboard() -> str:
    """Generate dashboard.html and return its absolute path."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    trades = _read_trades()
    decision = _read_json("latest_decision.json")
    config = _read_json("config.json")
    if not config:
        config = {"capital": 1000, "max_positions": 10, "max_sector_exposure": 3, "brokerage_fee_pct": 0.25}

    stats = _compute_stats(trades, config)

    data_blob = json.dumps({
        "config": config,
        "trades": trades,
        "decision": decision,
        "stats": stats,
        "generated_at": datetime.now().isoformat(),
    }, default=str)

    html = _build_html(data_blob)
    out_path = DATA_DIR / "dashboard.html"
    out_path.write_text(html, encoding="utf-8")
    return str(out_path.resolve())


def _build_html(data_json: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Swing Trader Dashboard</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
<style>
{_CSS}
</style>
</head>
<body>

<nav>
  <span class="logo">Swing Trader</span>
  <a href="#" class="tab-link active" data-tab="dashboard">Dashboard</a>
  <a href="#" class="tab-link" data-tab="scan">Scan</a>
  <a href="#" class="tab-link" data-tab="portfolio">Portfolio</a>
  <a href="#" class="tab-link" data-tab="journal">Journal</a>
  <a href="#" class="tab-link" data-tab="review">Review</a>
  <a href="#" class="tab-link" data-tab="settings">Settings</a>
</nav>

<div class="container">

<!-- DASHBOARD TAB -->
<div id="tab-dashboard" class="tab-content active">
  <h1>Dashboard</h1>
  <div id="stats-grid" class="grid grid-4"></div>
  <div class="card mt-2">
    <h3>Regime</h3>
    <div id="regime-summary"></div>
  </div>
  <div class="card mt-2">
    <h3>Open Positions</h3>
    <div id="dash-open-positions"></div>
  </div>
</div>

<!-- SCAN TAB -->
<div id="tab-scan" class="tab-content">
  <h1>Latest Scan Results</h1>
  <div id="scan-summary"></div>
  <div id="scan-picks"></div>
  <div id="scan-watchlist" class="mt-2"></div>
  <div id="scan-warnings" class="mt-2"></div>
</div>

<!-- PORTFOLIO TAB -->
<div id="tab-portfolio" class="tab-content">
  <h1>Portfolio</h1>
  <div id="portfolio-table"></div>
</div>

<!-- JOURNAL TAB -->
<div id="tab-journal" class="tab-content">
  <h1>Trade Journal</h1>
  <div id="journal-table"></div>
</div>

<!-- REVIEW TAB -->
<div id="tab-review" class="tab-content">
  <h1>Performance Review</h1>
  <div id="review-content"></div>
</div>

<!-- SETTINGS TAB -->
<div id="tab-settings" class="tab-content">
  <h1>Settings</h1>
  <div class="card" style="max-width:500px">
    <div class="form-group">
      <label>Capital ($)</label>
      <input type="number" id="cfg-capital" step="100">
    </div>
    <div class="form-group">
      <label>Max Positions</label>
      <input type="number" id="cfg-max-positions" step="1" min="1" max="20">
    </div>
    <div class="form-group">
      <label>Max Sector Exposure</label>
      <input type="number" id="cfg-max-sector" step="1" min="1" max="10">
    </div>
    <div class="form-group">
      <label>Brokerage Fee (%)</label>
      <input type="number" id="cfg-fee" step="0.01" min="0">
    </div>
    <button class="btn btn-primary mt-2" onclick="copyConfigCmd()">Copy Update Command</button>
    <div id="config-cmd-preview" class="mt-2" style="display:none">
      <pre class="card" style="font-size:0.85rem;white-space:pre-wrap;"></pre>
    </div>
  </div>
  <p class="text-dim mt-2" style="font-size:0.85rem">
    Changes are applied via CLI. Copy the command above and run it in your terminal.
  </p>
</div>

</div>

<script>
const DATA = {data_json};

// --- Tab navigation ---
document.querySelectorAll('.tab-link').forEach(link => {{
  link.addEventListener('click', e => {{
    e.preventDefault();
    document.querySelectorAll('.tab-link').forEach(l => l.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    link.classList.add('active');
    document.getElementById('tab-' + link.dataset.tab).classList.add('active');
  }});
}});

// --- Helpers ---
function $(sel) {{ return document.querySelector(sel); }}
function $$(sel) {{ return document.querySelectorAll(sel); }}
function esc(s) {{ const d = document.createElement('div'); d.textContent = s || ''; return d.innerHTML; }}
function fmt$(v) {{ return '$' + parseFloat(v || 0).toFixed(2); }}
function pctClass(v) {{ return parseFloat(v || 0) >= 0 ? 'text-green' : 'text-red'; }}

function copyToClip(text) {{
  navigator.clipboard.writeText(text).then(() => {{
    const btn = event.target;
    const orig = btn.textContent;
    btn.textContent = 'Copied!';
    setTimeout(() => btn.textContent = orig, 1500);
  }});
}}

// --- Dashboard ---
function renderDashboard() {{
  const s = DATA.stats;
  const pnlClass = s.total_pnl >= 0 ? 'green' : 'red';
  $('#stats-grid').innerHTML = `
    <div class="stat"><div class="label">Capital</div><div class="value blue font-mono">${{fmt$(s.capital)}}</div></div>
    <div class="stat"><div class="label">Deployed</div><div class="value cyan font-mono">${{fmt$(s.deployed)}}</div></div>
    <div class="stat"><div class="label">Cash</div><div class="value font-mono">${{fmt$(s.cash)}}</div></div>
    <div class="stat"><div class="label">Total P&L</div><div class="value ${{pnlClass}} font-mono">${{fmt$(s.total_pnl)}}</div></div>
  `;

  const d = DATA.decision || {{}};
  const regime = (d.regime_assessment || d.macro?.regime || 'N/A').toUpperCase();
  const regimeClass = regime.includes('BULL') ? 'bull' : regime.includes('BEAR') ? 'bear' : 'neutral';
  $('#regime-summary').innerHTML = `
    <span class="regime-badge ${{regimeClass}}"><span class="regime-dot"></span>${{esc(regime.substring(0,30))}}</span>
    <p class="text-dim mt-2" style="font-size:0.85rem">${{esc(d.analysis_summary || '')}}</p>
  `;

  renderOpenPositionsTable('#dash-open-positions');
}}

function renderOpenPositionsTable(selector) {{
  const open = DATA.trades.filter(t => !t.exit_date);
  if (!open.length) {{
    $(selector).innerHTML = '<p class="text-dim">No open positions.</p>';
    return;
  }}
  let html = `<table><thead><tr>
    <th>Ticker</th><th>Entry Date</th><th>Entry $</th><th>Shares</th>
    <th>Size $</th><th>Stop</th><th>Target</th>
  </tr></thead><tbody>`;
  open.forEach(t => {{
    html += `<tr>
      <td><strong>${{esc(t.ticker)}}</strong></td>
      <td>${{esc(t.entry_date)}}</td>
      <td class="mono">${{fmt$(t.entry_price)}}</td>
      <td class="mono">${{parseFloat(t.shares).toFixed(4)}}</td>
      <td class="mono">${{fmt$(t.position_usd)}}</td>
      <td class="mono text-red">${{t.stop_loss ? fmt$(t.stop_loss) : '-'}}</td>
      <td class="mono text-green">${{t.target ? fmt$(t.target) : '-'}}</td>
    </tr>`;
  }});
  html += '</tbody></table>';
  $(selector).innerHTML = html;
}}

// --- Scan ---
function renderScan() {{
  const d = DATA.decision || {{}};
  if (!d.picks) {{
    $('#scan-summary').innerHTML = '<p class="text-dim">No scan data. Run: python main.py scan</p>';
    return;
  }}

  $('#scan-summary').innerHTML = `
    <div class="card mb-2">
      <p>${{esc(d.analysis_summary || '')}}</p>
      <p class="text-dim mt-2">${{esc(d.regime_assessment || '')}}</p>
    </div>
  `;

  let picksHtml = '';
  (d.picks || []).forEach((p, i) => {{
    const action = (p.action || 'BUY').toLowerCase();
    const conv = (p.conviction || 'MEDIUM').toLowerCase();
    const entry = parseFloat(p.entry_price || 0);
    const stop = parseFloat(p.stop_loss || 0);
    const target = parseFloat(p.target || 0);
    const riskPct = entry > 0 ? ((entry - stop) / entry * 100).toFixed(1) : '0.0';
    const rewardPct = entry > 0 ? ((target - entry) / entry * 100).toFixed(1) : '0.0';
    const shares = entry > 0 ? (parseFloat(p.position_usd || 0) / entry).toFixed(4) : '0';
    const logCmd = `python main.py log-entry --ticker ${{p.ticker}} --price ${{entry}} --shares ${{shares}} --stop ${{stop}} --target ${{target}}`;

    picksHtml += `
    <div class="pick-card">
      <div class="pick-header">
        <span class="pick-rank">${{i + 1}}</span>
        <span class="pick-ticker">${{esc(p.ticker)}}</span>
        <span class="pick-action ${{action}}">${{action.toUpperCase()}}</span>
        <span class="conviction-${{conv}}" style="font-size:0.8rem;font-weight:600">${{(p.conviction || '').toUpperCase()}}</span>
      </div>
      <div class="pick-numbers">
        <div class="pick-num-item"><div class="num-label">Entry</div><div class="num-value">${{fmt$(entry)}}</div></div>
        <div class="pick-num-item"><div class="num-label">Stop</div><div class="num-value text-red">${{fmt$(stop)}} (-${{riskPct}}%)</div></div>
        <div class="pick-num-item"><div class="num-label">Target</div><div class="num-value text-green">${{fmt$(target)}} (+${{rewardPct}}%)</div></div>
        <div class="pick-num-item"><div class="num-label">R:R</div><div class="num-value">${{parseFloat(p.risk_reward_ratio || 0).toFixed(1)}}</div></div>
        <div class="pick-num-item"><div class="num-label">Size</div><div class="num-value">${{fmt$(p.position_usd)}}</div></div>
      </div>
      <p class="pick-reasoning">${{esc(p.reasoning)}}</p>
      <button class="btn btn-sm btn-outline mt-2" onclick="copyToClip('${{logCmd.replace(/'/g, "\\\\'")}}')">Copy Log Command</button>
    </div>`;
  }});
  $('#scan-picks').innerHTML = picksHtml;

  // Watchlist notes
  const notes = d.watchlist_notes || [];
  if (notes.length) {{
    let whtml = '<h3>Watchlist Notes</h3>';
    notes.forEach(n => {{
      whtml += `<div class="watchlist-note"><span class="wn-ticker">${{esc(n.ticker)}}</span>${{esc(n.note)}}</div>`;
    }});
    $('#scan-watchlist').innerHTML = whtml;
  }}

  // Risk warnings
  const warnings = d.risk_warnings || [];
  if (warnings.length) {{
    let whtml = '<h3>Risk Warnings</h3>';
    warnings.forEach(w => {{
      whtml += `<div class="risk-item">! ${{esc(w)}}</div>`;
    }});
    $('#scan-warnings').innerHTML = whtml;
  }}
}}

// --- Portfolio ---
function renderPortfolio() {{
  renderOpenPositionsTable('#portfolio-table');
}}

// --- Journal ---
function renderJournal() {{
  const trades = DATA.trades;
  if (!trades.length) {{
    $('#journal-table').innerHTML = '<p class="text-dim">No trades recorded. Use: python main.py log-entry ...</p>';
    return;
  }}
  let html = `<table><thead><tr>
    <th>Ticker</th><th>Entry</th><th>Exit</th><th>P&L $</th><th>P&L %</th><th>Reason</th><th>Status</th>
  </tr></thead><tbody>`;
  trades.forEach(t => {{
    const pnl = parseFloat(t.pnl || 0);
    const pnlPct = parseFloat(t.pnl_pct || 0);
    const cls = pnl > 0 ? 'text-green' : pnl < 0 ? 'text-red' : 'text-dim';
    const status = t.exit_date ? '<span class="tag tag-closed">CLOSED</span>' : '<span class="tag tag-open">OPEN</span>';
    html += `<tr>
      <td><strong>${{esc(t.ticker)}}</strong></td>
      <td class="mono">${{fmt$(t.entry_price)}} <span class="text-dim">(${{esc(t.entry_date)}})</span></td>
      <td class="mono">${{t.exit_date ? fmt$(t.exit_price) + ' <span class="text-dim">(' + esc(t.exit_date) + ')</span>' : '-'}}</td>
      <td class="mono ${{cls}}">${{t.exit_date ? fmt$(pnl) : '-'}}</td>
      <td class="mono ${{cls}}">${{t.exit_date ? pnlPct.toFixed(1) + '%' : '-'}}</td>
      <td>${{esc(t.exit_reason || '-')}}</td>
      <td>${{status}}</td>
    </tr>`;
  }});
  html += '</tbody></table>';
  $('#journal-table').innerHTML = html;
}}

// --- Review ---
function renderReview() {{
  const closed = DATA.trades.filter(t => t.exit_date);
  if (!closed.length) {{
    $('#review-content').innerHTML = '<p class="text-dim">No closed trades to review yet.</p>';
    return;
  }}

  const totalPnl = closed.reduce((s, t) => s + parseFloat(t.pnl || 0), 0);
  const winners = closed.filter(t => parseFloat(t.pnl || 0) > 0);
  const losers = closed.filter(t => parseFloat(t.pnl || 0) <= 0);
  const winRate = (winners.length / closed.length * 100).toFixed(1);
  const avgWin = winners.length ? (winners.reduce((s, t) => s + parseFloat(t.pnl), 0) / winners.length).toFixed(2) : '0.00';
  const avgLoss = losers.length ? (losers.reduce((s, t) => s + Math.abs(parseFloat(t.pnl)), 0) / losers.length).toFixed(2) : '0.00';
  const avgRR = parseFloat(avgLoss) > 0 ? (parseFloat(avgWin) / parseFloat(avgLoss)).toFixed(2) : '-';
  const capital = DATA.config.capital || 1000;
  const pnlPct = ((totalPnl / capital) * 100).toFixed(1);
  const pnlCls = totalPnl >= 0 ? 'text-green' : 'text-red';

  $('#review-content').innerHTML = `
    <div class="card">
      <div class="metric-row"><span class="metric-label">Total Trades</span><span class="metric-value">${{closed.length}}</span></div>
      <div class="metric-row"><span class="metric-label">Wins / Losses</span><span class="metric-value">${{winners.length}} / ${{losers.length}}</span></div>
      <div class="metric-row"><span class="metric-label">Win Rate</span><span class="metric-value">${{winRate}}%</span></div>
      <div class="metric-row"><span class="metric-label">Total P&L</span><span class="metric-value ${{pnlCls}}">${{fmt$(totalPnl)}} (${{pnlPct}}%)</span></div>
      <div class="metric-row"><span class="metric-label">Avg Win / Avg Loss</span><span class="metric-value">${{fmt$(avgWin)}} / ${{fmt$(avgLoss)}}</span></div>
      <div class="metric-row"><span class="metric-label">Avg R:R</span><span class="metric-value">${{avgRR}}x</span></div>
    </div>
  `;
}}

// --- Settings ---
function renderSettings() {{
  const c = DATA.config;
  $('#cfg-capital').value = c.capital || 1000;
  $('#cfg-max-positions').value = c.max_positions || 10;
  $('#cfg-max-sector').value = c.max_sector_exposure || 3;
  $('#cfg-fee').value = c.brokerage_fee_pct || 0.25;
}}

function copyConfigCmd() {{
  const parts = ['python main.py config'];
  const capital = parseFloat($('#cfg-capital').value);
  const maxPos = parseInt($('#cfg-max-positions').value);
  const maxSec = parseInt($('#cfg-max-sector').value);
  const fee = parseFloat($('#cfg-fee').value);
  const c = DATA.config;

  if (capital !== (c.capital || 1000)) parts.push('--capital ' + capital);
  if (maxPos !== (c.max_positions || 10)) parts.push('--max-positions ' + maxPos);
  if (maxSec !== (c.max_sector_exposure || 3)) parts.push('--max-sector-exposure ' + maxSec);
  if (fee !== (c.brokerage_fee_pct || 0.25)) parts.push('--brokerage-fee ' + fee);

  if (parts.length === 1) {{
    alert('No changes detected.');
    return;
  }}

  const cmd = parts.join(' ');
  navigator.clipboard.writeText(cmd);
  const preview = $('#config-cmd-preview');
  preview.style.display = 'block';
  preview.querySelector('pre').textContent = cmd + '\\n\\n(Copied to clipboard!)';
}}

// --- Init ---
renderDashboard();
renderScan();
renderPortfolio();
renderJournal();
renderReview();
renderSettings();
</script>
</body>
</html>"""


_CSS = """:root {
  --bg: #0f1117;
  --surface: #1a1d27;
  --surface2: #232734;
  --border: #2e3348;
  --text: #e4e6ef;
  --text-dim: #8b8fa3;
  --green: #22c55e;
  --green-dim: #16a34a;
  --red: #ef4444;
  --red-dim: #dc2626;
  --blue: #3b82f6;
  --yellow: #eab308;
  --cyan: #06b6d4;
  --purple: #a855f7;
  --radius: 10px;
  --font: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  --mono: 'JetBrains Mono', 'Fira Code', monospace;
}

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
  font-family: var(--font);
  background: var(--bg);
  color: var(--text);
  line-height: 1.6;
  min-height: 100vh;
}

nav {
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  padding: 0 2rem;
  display: flex;
  align-items: center;
  height: 56px;
  position: sticky;
  top: 0;
  z-index: 100;
}

nav .logo {
  font-weight: 700;
  font-size: 1.1rem;
  color: var(--cyan);
  margin-right: 2.5rem;
  letter-spacing: -0.02em;
}

nav a {
  color: var(--text-dim);
  text-decoration: none;
  padding: 0.5rem 1rem;
  font-size: 0.9rem;
  border-radius: 6px;
  transition: all 0.15s;
}

nav a:hover, nav a.active {
  color: var(--text);
  background: var(--surface2);
}

.container {
  max-width: 1200px;
  margin: 0 auto;
  padding: 2rem;
}

h1 { font-size: 1.6rem; font-weight: 700; margin-bottom: 1.5rem; letter-spacing: -0.02em; }
h2 { font-size: 1.2rem; font-weight: 600; margin-bottom: 1rem; color: var(--text-dim); }
h3 { font-size: 1rem; font-weight: 600; margin-bottom: 0.75rem; }

.tab-content { display: none; }
.tab-content.active { display: block; }

.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 1.25rem;
  margin-bottom: 1rem;
}

.grid { display: grid; gap: 1rem; }
.grid-2 { grid-template-columns: 1fr 1fr; }
.grid-3 { grid-template-columns: 1fr 1fr 1fr; }
.grid-4 { grid-template-columns: 1fr 1fr 1fr 1fr; }

@media (max-width: 768px) {
  .grid-2, .grid-3, .grid-4 { grid-template-columns: 1fr; }
  .pick-numbers { grid-template-columns: repeat(3, 1fr) !important; }
}

.stat {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 1.25rem;
  text-align: center;
}

.stat .value {
  font-size: 1.8rem;
  font-weight: 700;
  font-family: var(--mono);
  margin: 0.25rem 0;
}

.stat .label {
  font-size: 0.8rem;
  color: var(--text-dim);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.stat .value.green { color: var(--green); }
.stat .value.red { color: var(--red); }
.stat .value.blue { color: var(--blue); }
.stat .value.cyan { color: var(--cyan); }

.regime-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.4rem 1rem;
  border-radius: 20px;
  font-weight: 600;
  font-size: 0.85rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.regime-badge.bull { background: rgba(34,197,94,0.15); color: var(--green); border: 1px solid rgba(34,197,94,0.3); }
.regime-badge.bear { background: rgba(239,68,68,0.15); color: var(--red); border: 1px solid rgba(239,68,68,0.3); }
.regime-badge.neutral { background: rgba(234,179,8,0.15); color: var(--yellow); border: 1px solid rgba(234,179,8,0.3); }

.regime-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  animation: pulse 2s infinite;
}

.bull .regime-dot { background: var(--green); }
.bear .regime-dot { background: var(--red); }
.neutral .regime-dot { background: var(--yellow); }

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.6rem 1.25rem;
  border-radius: 8px;
  font-size: 0.875rem;
  font-weight: 600;
  border: none;
  cursor: pointer;
  transition: all 0.15s;
  text-decoration: none;
  color: #fff;
}

.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-primary { background: var(--blue); }
.btn-primary:hover:not(:disabled) { background: #2563eb; }
.btn-outline {
  background: transparent;
  border: 1px solid var(--border);
  color: var(--text);
}
.btn-outline:hover { background: var(--surface2); }
.btn-sm { padding: 0.35rem 0.75rem; font-size: 0.8rem; }

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.875rem;
}

th {
  text-align: left;
  padding: 0.75rem 1rem;
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-dim);
  border-bottom: 1px solid var(--border);
  font-weight: 600;
}

td {
  padding: 0.75rem 1rem;
  border-bottom: 1px solid var(--border);
  vertical-align: top;
}

tr:hover td { background: var(--surface2); }
td.mono { font-family: var(--mono); font-size: 0.85rem; }

.pick-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 1.25rem;
  margin-bottom: 0.75rem;
  transition: border-color 0.15s;
}

.pick-card:hover { border-color: var(--blue); }

.pick-header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
}

.pick-rank {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--surface2);
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 0.8rem;
  color: var(--text-dim);
}

.pick-ticker { font-weight: 700; font-size: 1.1rem; }

.pick-action {
  font-size: 0.75rem;
  font-weight: 700;
  padding: 0.15rem 0.6rem;
  border-radius: 4px;
  text-transform: uppercase;
}

.pick-action.buy { background: rgba(34,197,94,0.15); color: var(--green); }
.pick-action.sell { background: rgba(239,68,68,0.15); color: var(--red); }
.pick-action.hold { background: rgba(6,182,212,0.15); color: var(--cyan); }

.conviction-high { color: var(--green); }
.conviction-medium { color: var(--yellow); }
.conviction-low { color: var(--red); }

.pick-numbers {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 0.75rem;
  margin-bottom: 0.75rem;
}

.pick-num-item .num-label {
  font-size: 0.7rem;
  color: var(--text-dim);
  text-transform: uppercase;
}

.pick-num-item .num-value {
  font-family: var(--mono);
  font-weight: 600;
  font-size: 0.95rem;
}

.pick-reasoning {
  font-size: 0.85rem;
  color: var(--text-dim);
  line-height: 1.5;
}

.form-group { margin-bottom: 1rem; }

.form-group label {
  display: block;
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--text-dim);
  margin-bottom: 0.3rem;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

input, select, textarea {
  width: 100%;
  padding: 0.6rem 0.8rem;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface2);
  color: var(--text);
  font-size: 0.9rem;
  font-family: var(--font);
  outline: none;
  transition: border-color 0.15s;
}

input:focus, select:focus, textarea:focus { border-color: var(--blue); }

.watchlist-note {
  padding: 0.75rem;
  border-left: 3px solid var(--yellow);
  margin-bottom: 0.5rem;
  background: rgba(234,179,8,0.05);
  border-radius: 0 6px 6px 0;
}

.watchlist-note .wn-ticker { font-weight: 700; margin-right: 0.5rem; }

.risk-item {
  padding: 0.5rem 0;
  color: var(--red);
  font-size: 0.875rem;
}

.metric-row {
  display: flex;
  justify-content: space-between;
  padding: 0.6rem 0;
  border-bottom: 1px solid var(--border);
  font-size: 0.9rem;
}

.metric-row:last-child { border-bottom: none; }
.metric-label { color: var(--text-dim); }
.metric-value { font-weight: 600; font-family: var(--mono); }

.tag {
  display: inline-block;
  padding: 0.15rem 0.5rem;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 600;
}

.tag-open { background: rgba(6,182,212,0.15); color: var(--cyan); }
.tag-closed { background: rgba(139,143,163,0.15); color: var(--text-dim); }

.text-green { color: var(--green); }
.text-red { color: var(--red); }
.text-dim { color: var(--text-dim); }
.font-mono { font-family: var(--mono); }
.mt-2 { margin-top: 1rem; }
.mb-2 { margin-bottom: 1rem; }
"""
