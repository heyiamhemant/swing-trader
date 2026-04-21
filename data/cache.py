import math
import sqlite3
import json
import time
from pathlib import Path

DB_PATH = Path(__file__).parent / "swing_trader.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS price_cache (
    ticker TEXT NOT NULL,
    date TEXT NOT NULL,
    open REAL, high REAL, low REAL, close REAL, volume INTEGER,
    PRIMARY KEY (ticker, date)
);

CREATE TABLE IF NOT EXISTS price_cache_meta (
    ticker TEXT PRIMARY KEY,
    last_fetched REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS fundamental_cache (
    ticker TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    fetched_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS macro_cache (
    series_id TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    fetched_at REAL NOT NULL
);
"""


def _sanitize_for_json(obj):
    """Replace NaN/Inf float values with None before JSON serialization."""
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_for_json(v) for v in obj]
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    return obj


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.executescript(_SCHEMA)
    return conn


def get_cached_prices(ticker: str, start: str, end: str, max_age_hours: float = 24) -> list[dict] | None:
    conn = get_connection()
    meta = conn.execute(
        "SELECT last_fetched FROM price_cache_meta WHERE ticker=?", (ticker,)
    ).fetchone()
    if meta is None:
        conn.close()
        return None
    age_hours = (time.time() - meta["last_fetched"]) / 3600
    if age_hours > max_age_hours:
        conn.close()
        return None

    rows = conn.execute(
        "SELECT * FROM price_cache WHERE ticker=? AND date>=? AND date<=? ORDER BY date",
        (ticker, start, end),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows] if rows else None


def store_prices(ticker: str, rows: list[dict]) -> None:
    conn = get_connection()
    conn.executemany(
        "INSERT OR REPLACE INTO price_cache (ticker, date, open, high, low, close, volume) "
        "VALUES (:ticker, :date, :open, :high, :low, :close, :volume)",
        rows,
    )
    conn.execute(
        "INSERT OR REPLACE INTO price_cache_meta (ticker, last_fetched) VALUES (?, ?)",
        (ticker, time.time()),
    )
    conn.commit()
    conn.close()


def get_cached_fundamentals(ticker: str, max_age_hours: float = 12) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT data, fetched_at FROM fundamental_cache WHERE ticker=?", (ticker,)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    age_hours = (time.time() - row["fetched_at"]) / 3600
    if age_hours > max_age_hours:
        return None
    return json.loads(row["data"])


def store_fundamentals(ticker: str, data: dict) -> None:
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO fundamental_cache (ticker, data, fetched_at) VALUES (?, ?, ?)",
        (ticker, json.dumps(_sanitize_for_json(data)), time.time()),
    )
    conn.commit()
    conn.close()


def get_cached_macro(series_id: str, max_age_hours: float = 12) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT data, fetched_at FROM macro_cache WHERE series_id=?", (series_id,)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    age_hours = (time.time() - row["fetched_at"]) / 3600
    if age_hours > max_age_hours:
        return None
    return json.loads(row["data"])


def store_macro(series_id: str, data: dict) -> None:
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO macro_cache (series_id, data, fetched_at) VALUES (?, ?, ?)",
        (series_id, json.dumps(_sanitize_for_json(data)), time.time()),
    )
    conn.commit()
    conn.close()
