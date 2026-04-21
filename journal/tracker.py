"""
Trade journal backed by CSV files.

Primary storage: data/trades.csv
"""

import csv
import json
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
TRADES_CSV = DATA_DIR / "trades.csv"

FIELDNAMES = [
    "id", "ticker", "entry_date", "entry_price", "shares", "position_usd",
    "stop_loss", "target", "composite_score", "technical_score",
    "fundamental_score", "macro_regime", "sector", "exit_date", "exit_price",
    "exit_reason", "pnl", "pnl_pct", "notes",
]


def _ensure_csv():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not TRADES_CSV.exists():
        with open(TRADES_CSV, "w", newline="") as f:
            csv.DictWriter(f, fieldnames=FIELDNAMES).writeheader()


def _read_all() -> list[dict]:
    _ensure_csv()
    with open(TRADES_CSV, newline="") as f:
        return list(csv.DictReader(f))


def _write_all(rows: list[dict]):
    _ensure_csv()
    with open(TRADES_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def _next_id(rows: list[dict]) -> int:
    if not rows:
        return 1
    return max(int(r["id"]) for r in rows) + 1


def _to_float(val, default=None):
    if val is None or val == "":
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def log_entry(
    ticker: str,
    price: float,
    shares: float,
    position_usd: float,
    stop_loss: float,
    target: float,
    scores: dict | None = None,
    regime: str = "",
    sector: str = "",
    notes: str = "",
) -> int:
    rows = _read_all()
    scores = scores or {}
    trade_id = _next_id(rows)

    rows.append({
        "id": trade_id,
        "ticker": ticker,
        "entry_date": datetime.now().strftime("%Y-%m-%d"),
        "entry_price": round(price, 2),
        "shares": round(shares, 4),
        "position_usd": round(position_usd, 2),
        "stop_loss": round(stop_loss, 2),
        "target": round(target, 2),
        "composite_score": scores.get("composite", ""),
        "technical_score": scores.get("technical", ""),
        "fundamental_score": scores.get("fundamental", ""),
        "macro_regime": regime,
        "sector": sector,
        "exit_date": "",
        "exit_price": "",
        "exit_reason": "",
        "pnl": "",
        "pnl_pct": "",
        "notes": notes,
    })

    _write_all(rows)
    return trade_id


def log_exit(
    ticker: str,
    price: float,
    reason: str = "manual",
    notes: str = "",
) -> dict | None:
    rows = _read_all()

    target_idx = None
    for i in range(len(rows) - 1, -1, -1):
        if rows[i]["ticker"] == ticker and not rows[i].get("exit_date"):
            target_idx = i
            break

    if target_idx is None:
        return None

    row = rows[target_idx]
    entry_price = float(row["entry_price"])
    shares_val = float(row["shares"])
    pnl = round((price - entry_price) * shares_val, 2)
    pnl_pct = round(((price - entry_price) / entry_price) * 100, 2)

    old_notes = row.get("notes", "")
    combined_notes = f"{old_notes} | {notes}" if old_notes and notes else notes or old_notes

    rows[target_idx]["exit_date"] = datetime.now().strftime("%Y-%m-%d")
    rows[target_idx]["exit_price"] = round(price, 2)
    rows[target_idx]["exit_reason"] = reason
    rows[target_idx]["pnl"] = pnl
    rows[target_idx]["pnl_pct"] = pnl_pct
    rows[target_idx]["notes"] = combined_notes

    _write_all(rows)

    return {
        "trade_id": int(row["id"]),
        "ticker": ticker,
        "entry_price": entry_price,
        "exit_price": price,
        "pnl": pnl,
        "pnl_pct": pnl_pct,
        "reason": reason,
    }


def get_open_positions() -> list[dict]:
    rows = _read_all()
    result = []
    for r in rows:
        if not r.get("exit_date"):
            result.append(_normalize_row(r))
    return result


def get_closed_trades(quarter: str | None = None) -> list[dict]:
    rows = _read_all()
    closed = [r for r in rows if r.get("exit_date")]

    if quarter:
        year, q = quarter.split("Q")
        q_num = int(q)
        start_month = (q_num - 1) * 3 + 1
        end_month = start_month + 2
        start_date = f"{year}-{start_month:02d}-01"
        end_date = f"{year}-{end_month:02d}-31"
        closed = [r for r in closed if start_date <= r["exit_date"] <= end_date]

    return [_normalize_row(r) for r in closed]


def get_all_trades() -> list[dict]:
    return [_normalize_row(r) for r in _read_all()]


def save_quarterly_review(review: dict) -> None:
    """Append a quarterly review to data/quarterly_reviews.json."""
    if review.get("total_trades", 0) == 0:
        return

    path = DATA_DIR / "quarterly_reviews.json"
    reviews = []
    if path.exists():
        try:
            reviews = json.loads(path.read_text())
        except (json.JSONDecodeError, ValueError):
            reviews = []

    reviews = [r for r in reviews if r.get("quarter") != review["quarter"]]
    reviews.append(review)

    path.write_text(json.dumps(reviews, indent=2), encoding="utf-8")


def save_portfolio_snapshot(regime: str, total_value: float, cash: float, positions: list[dict]) -> None:
    path = DATA_DIR / "snapshots.json"
    snapshots = []
    if path.exists():
        try:
            snapshots = json.loads(path.read_text())
        except (json.JSONDecodeError, ValueError):
            snapshots = []

    snapshots.append({
        "snapshot_date": datetime.now().strftime("%Y-%m-%d"),
        "regime": regime,
        "total_value": total_value,
        "cash": cash,
        "positions": positions,
    })

    path.write_text(json.dumps(snapshots, indent=2), encoding="utf-8")


def _normalize_row(row: dict) -> dict:
    """Convert CSV string values back to appropriate Python types."""
    return {
        "id": int(row["id"]),
        "ticker": row["ticker"],
        "entry_date": row["entry_date"],
        "entry_price": float(row["entry_price"]),
        "shares": float(row["shares"]),
        "position_usd": float(row["position_usd"]),
        "stop_loss": _to_float(row.get("stop_loss")),
        "target": _to_float(row.get("target")),
        "composite_score": _to_float(row.get("composite_score")),
        "technical_score": _to_float(row.get("technical_score")),
        "fundamental_score": _to_float(row.get("fundamental_score")),
        "macro_regime": row.get("macro_regime", ""),
        "sector": row.get("sector", ""),
        "exit_date": row.get("exit_date") or None,
        "exit_price": _to_float(row.get("exit_price")),
        "exit_reason": row.get("exit_reason") or None,
        "pnl": _to_float(row.get("pnl")),
        "pnl_pct": _to_float(row.get("pnl_pct")),
        "notes": row.get("notes", ""),
    }
