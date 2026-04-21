import logging
import os
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf

from data import cache
from config.loader import get_config, get_watchlist_raw

logger = logging.getLogger(__name__)


def load_watchlist() -> dict[str, list[str]]:
    raw = get_watchlist_raw()
    flat: dict[str, list[str]] = {}
    for category in ("sectors", "etfs"):
        for group_name, tickers in raw.get(category, {}).items():
            flat[group_name] = tickers
    return flat


def all_tickers() -> list[str]:
    watchlist = load_watchlist()
    seen: set[str] = set()
    result: list[str] = []
    for group_name, tickers in watchlist.items():
        for t in tickers:
            if t in seen:
                logger.warning("Duplicate ticker %s in group %s — skipping", t, group_name)
                continue
            seen.add(t)
            result.append(t)
    return result


def ticker_to_sector() -> dict[str, str]:
    watchlist = load_watchlist()
    mapping: dict[str, str] = {}
    for group_name, tickers in watchlist.items():
        for t in tickers:
            if t not in mapping:
                mapping[t] = group_name
    return mapping


def fetch_price_data(
    ticker: str, days: int | None = None, use_cache: bool = True
) -> pd.DataFrame:
    cfg = get_config()["data"]
    days = days or cfg.get("price_lookback_days", 365)
    cache_ttl = cfg.get("cache_expiry_hours", 24)

    end = datetime.now()
    start = end - timedelta(days=days)
    start_str = start.strftime("%Y-%m-%d")
    end_str = end.strftime("%Y-%m-%d")

    if use_cache:
        cached = cache.get_cached_prices(ticker, start_str, end_str, max_age_hours=cache_ttl)
        if cached and len(cached) > 50:
            df = pd.DataFrame(cached)
            df["date"] = pd.to_datetime(df["date"])
            df.set_index("date", inplace=True)
            return df

    tk = yf.Ticker(ticker)
    df = tk.history(start=start_str, end=end_str)
    if df.empty:
        return df

    df.index = df.index.tz_localize(None)
    df.columns = [c.lower() for c in df.columns]
    df = df[["open", "high", "low", "close", "volume"]]

    rows = []
    for dt, row in df.iterrows():
        rows.append({
            "ticker": ticker,
            "date": dt.strftime("%Y-%m-%d"),
            "open": row["open"],
            "high": row["high"],
            "low": row["low"],
            "close": row["close"],
            "volume": int(row["volume"]),
        })
    if rows:
        cache.store_prices(ticker, rows)

    return df


def fetch_fundamentals(ticker: str, use_cache: bool = True) -> dict:
    if use_cache:
        cached = cache.get_cached_fundamentals(ticker, max_age_hours=168)
        if cached:
            return cached

    tk = yf.Ticker(ticker)
    info = tk.info or {}

    data = {
        "ticker": ticker,
        "pe_trailing": info.get("trailingPE"),
        "pe_forward": info.get("forwardPE"),
        "peg_ratio": info.get("pegRatio"),
        "revenue_growth": info.get("revenueGrowth"),
        "earnings_growth": info.get("earningsGrowth"),
        "profit_margin": info.get("profitMargins"),
        "debt_to_equity": info.get("debtToEquity"),
        "return_on_equity": info.get("returnOnEquity"),
        "free_cash_flow": info.get("freeCashflow"),
        "market_cap": info.get("marketCap"),
        "sector": info.get("sector", ""),
        "industry": info.get("industry", ""),
        "short_name": info.get("shortName", ticker),
        "current_price": info.get("currentPrice") or info.get("regularMarketPrice"),
        "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
        "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
    }

    cache.store_fundamentals(ticker, data)
    return data


def fetch_fred_series(series_id: str, use_cache: bool = True) -> pd.Series | None:
    """Fetch a FRED series. Returns None if API key is missing."""
    if use_cache:
        cached = cache.get_cached_macro(series_id)
        if cached:
            s = pd.Series(cached)
            s.index = pd.to_datetime(s.index)
            return s

    api_key = os.environ.get("FRED_API_KEY")
    if not api_key:
        return None

    try:
        from fredapi import Fred
        fred = Fred(api_key=api_key)
        s = fred.get_series(series_id)
        if s is not None and not s.empty:
            store_data = {d.strftime("%Y-%m-%d"): float(v) for d, v in s.items() if pd.notna(v)}
            cache.store_macro(series_id, store_data)
            return s
    except Exception:
        pass
    return None
