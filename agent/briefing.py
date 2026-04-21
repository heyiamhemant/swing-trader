"""
Builds a structured data briefing for Claude to make trading decisions.

Collects all quantitative data (technicals, fundamentals, macro) and
formats it into a comprehensive report that Claude can reason over.

Uses ThreadPoolExecutor for parallel data fetching across 450+ stocks.
"""

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Callable

import pandas as pd

from config.loader import get_config
from data.fetcher import (
    all_tickers,
    fetch_fundamentals,
    fetch_price_data,
    ticker_to_sector,
)
from analysis.technical import compute_technical_score, find_support_resistance
from analysis.fundamental import compute_fundamental_score
from analysis.macro import detect_regime, compute_macro_score
from portfolio.risk import compute_levels

MAX_WORKERS = 10
TOP_N_FOR_CLAUDE = 60


def build_briefing(
    verbose: bool = False,
    progress_cb: Callable[[str], None] | None = None,
) -> dict:
    """
    Gather all data and build a complete briefing dict.

    Uses parallel fetching for speed. Sends only the top N stocks
    to Claude to keep prompt size manageable.
    """
    def _progress(msg: str):
        if progress_cb:
            progress_cb(msg)
        if verbose:
            print(msg)

    _progress("Detecting macro regime...")
    regime = detect_regime()
    macro_score = compute_macro_score(regime)

    tickers = all_tickers()
    sector_map = ticker_to_sector()
    total = len(tickers)
    _progress(f"Scanning {total} stocks with {MAX_WORKERS} parallel workers...")

    stocks = []
    done = 0
    failed = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {
            pool.submit(analyze_single_stock, ticker, sector_map, macro_score, verbose): ticker
            for ticker in tickers
        }

        for future in as_completed(futures):
            done += 1
            ticker = futures[future]
            try:
                result = future.result()
                if result:
                    stocks.append(result)
            except Exception as e:
                failed += 1
                if verbose:
                    print(f"  [fail] {ticker}: {e}")

            if done % 25 == 0 or done == total:
                _progress(f"Progress: {done}/{total} stocks ({len(stocks)} valid, {failed} failed)")

    cfg = get_config()
    weights = cfg["scoring"]["weights"]
    w_tech = weights["technical"]
    w_fund = weights["fundamental"]
    w_macro = weights["macro"]

    for s in stocks:
        sc = s["scores"]
        s["_sort_score"] = sc["technical"] * w_tech + sc["fundamental"] * w_fund + sc["macro"] * w_macro

    stocks.sort(key=lambda s: s["_sort_score"], reverse=True)

    top_stocks = stocks[:TOP_N_FOR_CLAUDE]
    for s in stocks:
        s.pop("_sort_score", None)

    _progress(f"Scan complete: {len(stocks)} valid stocks. Top {len(top_stocks)} sent to Claude.")

    cap = cfg["capital"]
    return {
        "generated_at": datetime.now().isoformat(),
        "metadata": {
            "capital": cap["total"],
            "max_positions": cap["max_positions"],
            "max_sector_exposure": cap["max_sector_exposure"],
            "rebalance_frequency": "quarterly",
            "platform": "Vested Finance (fractional shares, $1 minimum)",
            "brokerage_fee": "0.25% per trade",
            "total_universe": total,
            "stocks_analyzed": len(stocks),
            "top_n_shown": len(top_stocks),
        },
        "macro": {
            "regime": regime["regime"],
            "allocation_pct": regime["allocation_pct"],
            "tilt": regime["tilt"],
            "bull_signals": regime["bull_signals"],
            "signals": {
                k: v["detail"] for k, v in regime["signals"].items()
            },
        },
        "macro_raw": regime,
        "stocks": top_stocks,
        "all_stocks_count": len(stocks),
        "top_n_sent_to_claude": len(top_stocks),
    }


def analyze_single_stock(
    ticker: str, sector_map: dict, macro_score: float, verbose: bool
) -> dict | None:
    try:
        df = fetch_price_data(ticker, days=365)
        if df.empty or len(df) < 50:
            return None

        fundamentals = fetch_fundamentals(ticker)
        tech_result = compute_technical_score(df)
        fund_result = compute_fundamental_score(fundamentals)

        if not tech_result["valid"]:
            return None

        price = float(df["close"].iloc[-1])
        atr = tech_result["indicators"].get("atr")
        risk = compute_levels(price, atr, df)

        supports, resistances = find_support_resistance(df)

        high_52w = float(df["high"].max())
        low_52w = float(df["low"].min())
        pct_from_high = ((price - high_52w) / high_52w) * 100
        sma_20 = float(df["close"].rolling(20).mean().iloc[-1])
        price_change_5d = ((price / float(df["close"].iloc[-6])) - 1) * 100 if len(df) > 5 else 0
        price_change_20d = ((price / float(df["close"].iloc[-21])) - 1) * 100 if len(df) > 20 else 0

        stock = {
            "ticker": ticker,
            "name": fundamentals.get("short_name", ticker),
            "sector": sector_map.get(ticker, fundamentals.get("sector", "unknown")),
            "price": round(price, 2),
            "price_context": {
                "52w_high": round(high_52w, 2),
                "52w_low": round(low_52w, 2),
                "pct_from_52w_high": round(pct_from_high, 1),
                "sma_20": round(sma_20, 2),
                "change_5d_pct": round(price_change_5d, 1),
                "change_20d_pct": round(price_change_20d, 1),
            },
            "scores": {
                "technical": tech_result["score"],
                "fundamental": fund_result["score"],
                "macro": round(macro_score, 2),
            },
            "technical_detail": tech_result["details"],
            "indicators": tech_result["indicators"],
            "fundamental_detail": fund_result.get("details", {}),
            "fundamentals_raw": fund_result.get("fundamentals", {}),
            "support_levels": [round(s, 2) for s in sorted(supports, reverse=True)[:3]],
            "resistance_levels": [round(r, 2) for r in sorted(resistances)[:3]],
            "quantitative_risk": risk,
        }

        return stock

    except Exception as e:
        if verbose:
            print(f"  [warn] {ticker}: {e}")
        return None


def briefing_to_text(briefing: dict) -> str:
    """Convert the briefing dict into a human-readable text report for Claude."""
    lines = []
    lines.append("=" * 70)
    lines.append("SWING TRADING DATA BRIEFING")
    lines.append(f"Generated: {briefing['generated_at']}")
    lines.append("=" * 70)

    meta = briefing["metadata"]
    lines.append(f"\nCAPITAL: ${meta['capital']} | MAX POSITIONS: {meta['max_positions']}")
    lines.append(f"SECTOR CAP: {meta['max_sector_exposure']} per sector | PLATFORM: {meta['platform']}")
    lines.append(f"UNIVERSE: {meta.get('total_universe', '?')} tickers scanned, top {meta.get('top_n_shown', '?')} shown below")

    macro = briefing["macro"]
    lines.append(f"\n{'='*70}")
    lines.append(f"MACRO REGIME: {macro['regime'].upper()} (allocation {macro['allocation_pct']*100:.0f}%, tilt: {macro['tilt']})")
    lines.append(f"Bull signals: {macro['bull_signals']}/3")
    for name, detail in macro["signals"].items():
        lines.append(f"  - {name}: {detail}")

    lines.append(f"\n{'='*70}")
    lines.append(f"TOP STOCKS BY COMPOSITE SCORE ({briefing.get('top_n_sent_to_claude', '?')} of {briefing.get('all_stocks_count', '?')} analyzed)")
    lines.append("=" * 70)

    for s in briefing["stocks"]:
        lines.append(f"\n--- {s['ticker']} ({s['name']}) | Sector: {s['sector']} ---")
        lines.append(f"  Price: ${s['price']}  |  5d: {s['price_context']['change_5d_pct']:+.1f}%  |  20d: {s['price_context']['change_20d_pct']:+.1f}%")
        lines.append(f"  52w Range: ${s['price_context']['52w_low']} - ${s['price_context']['52w_high']} ({s['price_context']['pct_from_52w_high']:+.1f}% from high)")

        sc = s["scores"]
        lines.append(f"  Scores -> Tech: {sc['technical']:.1f} | Fund: {sc['fundamental']:.1f} | Macro: {sc['macro']:.1f}")

        td = s["technical_detail"]
        lines.append(f"  Tech breakdown -> RSI: {td.get('rsi','-')} | MACD: {td.get('macd','-')} | EMA: {td.get('ema','-')} | BB: {td.get('bollinger','-')} | Vol: {td.get('volume','-')} | ADX: {td.get('adx','-')} | S/R: {td.get('support_resistance','-')}")

        ind = s["indicators"]
        lines.append(f"  Indicators -> RSI: {ind.get('rsi','-')} | MACD hist: {ind.get('macd_hist','-')} | ADX: {ind.get('adx','-')} | ATR: {ind.get('atr','-')} | Vol ratio: {ind.get('vol_ratio','-')}")

        fr = s.get("fundamentals_raw", {})
        lines.append(f"  Fundamentals -> P/E: {fr.get('pe','-')} | Rev growth: {fr.get('revenue_growth','-')} | EPS growth: {fr.get('earnings_growth','-')} | D/E: {fr.get('debt_to_equity','-')} | ROE: {fr.get('roe','-')} | FCF: {fr.get('fcf','-')}")

        if s["support_levels"]:
            lines.append(f"  Support: {s['support_levels']}")
        if s["resistance_levels"]:
            lines.append(f"  Resistance: {s['resistance_levels']}")

        risk = s["quantitative_risk"]
        lines.append(f"  Quant risk -> Stop: ${risk['stop_loss']} ({risk['risk_pct']:.1f}%) | Target: ${risk['target']} ({risk['reward_pct']:.1f}%) | R:R: {risk['rr_ratio']:.1f}")

    return "\n".join(lines)
