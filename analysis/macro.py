import pandas as pd

from config.loader import get_config
from data.fetcher import fetch_price_data, fetch_fred_series


def detect_regime() -> dict:
    """
    Determine the current macro regime: bull, neutral, or bear.

    Signals checked:
    1. SPY vs 200 EMA (trend)
    2. VIX level (fear gauge)
    3. Yield curve 10Y-2Y spread (recession signal)

    Returns a dict with regime name, allocation %, tilt, and signal details.
    """
    params = get_config()
    macro_params = params["macro"]["regimes"]

    signals = {
        "spy_trend": _check_spy_trend(),
        "vix_level": _check_vix(macro_params),
        "yield_curve": _check_yield_curve(),
    }

    known = [s for s in signals.values() if s["bullish"] is not None]
    bull_count = sum(1 for s in known if s["bullish"])

    if not known:
        regime = "neutral"
    elif bull_count / len(known) >= 0.67:
        regime = "bull"
    elif bull_count / len(known) <= 0.33:
        regime = "bear"
    else:
        regime = "neutral"

    regime_config = macro_params[regime]

    return {
        "regime": regime,
        "allocation_pct": regime_config["allocation_pct"],
        "tilt": regime_config["tilt"],
        "signals": signals,
        "bull_signals": bull_count,
    }


def compute_macro_score(regime_data: dict) -> float:
    """Convert regime data to a 0-100 score for the composite scorer."""
    regime = regime_data["regime"]
    if regime == "bull":
        return 85.0
    if regime == "neutral":
        return 55.0
    return 25.0


def _check_spy_trend() -> dict:
    try:
        df = fetch_price_data("SPY", days=365)
        if df.empty or len(df) < 200:
            return {"bullish": None, "detail": "insufficient SPY data — unknown"}

        import ta
        ema_200 = ta.trend.EMAIndicator(df["close"], window=200).ema_indicator()
        price = df["close"].iloc[-1]
        ema_val = ema_200.iloc[-1]

        bullish = price > ema_val
        pct_above = ((price - ema_val) / ema_val) * 100

        return {
            "bullish": bullish,
            "detail": f"SPY ${price:.2f} {'above' if bullish else 'below'} 200 EMA ${ema_val:.2f} ({pct_above:+.1f}%)",
        }
    except Exception as e:
        return {"bullish": None, "detail": f"error fetching SPY: {e}"}


def _check_vix(macro_params: dict) -> dict:
    try:
        # Try FRED first, fall back to yfinance ^VIX
        vix_series = fetch_fred_series("VIXCLS")
        if vix_series is not None and not vix_series.empty:
            vix = float(vix_series.dropna().iloc[-1])
        else:
            df = fetch_price_data("^VIX", days=30, use_cache=False)
            if df.empty:
                return {"bullish": None, "detail": "VIX unavailable — unknown"}
            vix = float(df["close"].iloc[-1])

        bull_threshold = macro_params["bull"]["vix_below"]
        bear_threshold = macro_params["bear"]["vix_above"]

        if vix < bull_threshold:
            return {"bullish": True, "detail": f"VIX {vix:.1f} (low fear, < {bull_threshold})"}
        if vix > bear_threshold:
            return {"bullish": False, "detail": f"VIX {vix:.1f} (high fear, > {bear_threshold})"}
        return {"bullish": True, "detail": f"VIX {vix:.1f} (moderate, between {bull_threshold}-{bear_threshold})"}

    except Exception as e:
        return {"bullish": None, "detail": f"VIX error: {e}"}


def _check_yield_curve() -> dict:
    try:
        spread = fetch_fred_series("T10Y2Y")
        if spread is None or spread.empty:
            return {"bullish": None, "detail": "yield curve data unavailable — unknown"}

        latest = float(spread.dropna().iloc[-1])
        bullish = latest > 0

        return {
            "bullish": bullish,
            "detail": f"10Y-2Y spread {latest:.2f}% ({'normal' if bullish else 'INVERTED'})",
        }
    except Exception as e:
        return {"bullish": None, "detail": f"yield curve error: {e}"}
