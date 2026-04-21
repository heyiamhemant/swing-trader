import numpy as np
import pandas as pd
import ta

from config.loader import get_config


def _load_params() -> dict:
    return get_config()["technical"]


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add all technical indicator columns to a price DataFrame."""
    if df.empty or len(df) < 50:
        return df

    p = _load_params()
    c, h, l, v = df["close"], df["high"], df["low"], df["volume"]

    df["rsi"] = ta.momentum.RSIIndicator(c, window=p["rsi"]["period"]).rsi()
    macd = ta.trend.MACD(c, window_slow=p["macd"]["slow"], window_fast=p["macd"]["fast"], window_sign=p["macd"]["signal"])
    df["macd_line"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()
    df["macd_hist"] = macd.macd_diff()

    df["ema_short"] = ta.trend.EMAIndicator(c, window=p["ema"]["short"]).ema_indicator()
    df["ema_long"] = ta.trend.EMAIndicator(c, window=p["ema"]["long"]).ema_indicator()

    bb = ta.volatility.BollingerBands(c, window=p["bollinger"]["period"], window_dev=p["bollinger"]["std_dev"])
    df["bb_upper"] = bb.bollinger_hband()
    df["bb_lower"] = bb.bollinger_lband()
    df["bb_middle"] = bb.bollinger_mavg()
    df["bb_pct"] = bb.bollinger_pband()

    df["vol_sma"] = v.rolling(window=p["volume"]["avg_period"]).mean()
    df["vol_ratio"] = v / df["vol_sma"]

    adx = ta.trend.ADXIndicator(h, l, c, window=p["adx"]["period"])
    df["adx"] = adx.adx()

    df["atr"] = ta.volatility.AverageTrueRange(h, l, c, window=14).average_true_range()

    return df


def find_support_resistance(df: pd.DataFrame, lookback: int = 60) -> tuple[list[float], list[float]]:
    """Identify key support and resistance levels from recent price pivots."""
    if len(df) < lookback:
        lookback = len(df)

    recent = df.tail(lookback)
    highs = recent["high"].values
    lows = recent["low"].values
    supports: list[float] = []
    resistances: list[float] = []

    for i in range(2, len(highs) - 2):
        if highs[i] > highs[i - 1] and highs[i] > highs[i - 2] and highs[i] > highs[i + 1] and highs[i] > highs[i + 2]:
            resistances.append(float(highs[i]))
        if lows[i] < lows[i - 1] and lows[i] < lows[i - 2] and lows[i] < lows[i + 1] and lows[i] < lows[i + 2]:
            supports.append(float(lows[i]))

    return supports, resistances


def score_rsi(df: pd.DataFrame, params: dict) -> float:
    rsi = df["rsi"].iloc[-1]
    if pd.isna(rsi):
        return 50.0

    p = params["rsi"]
    low, high = p["buy_zone_low"], p["buy_zone_high"]

    if low <= rsi <= high:
        return 100.0
    elif rsi < low:
        # Extremely oversold — could be falling knife, partial credit
        return 60.0
    elif high < rsi < p["overbought"]:
        # Trending up but not ideal entry
        return max(0, 80 - (rsi - high) * 2)
    else:
        # Overbought
        return max(0, 30 - (rsi - p["overbought"]))


def score_macd(df: pd.DataFrame) -> float:
    if len(df) < 2:
        return 50.0

    curr_hist = df["macd_hist"].iloc[-1]
    prev_hist = df["macd_hist"].iloc[-2]

    if pd.isna(curr_hist) or pd.isna(prev_hist):
        return 50.0

    # Bullish crossover: histogram flips positive
    if curr_hist > 0 and prev_hist <= 0:
        return 100.0
    # Histogram rising (momentum building)
    if curr_hist > prev_hist and curr_hist > 0:
        return 80.0
    if curr_hist > prev_hist and curr_hist <= 0:
        return 65.0
    # Bearish crossover
    if curr_hist < 0 and prev_hist >= 0:
        return 10.0
    # Histogram falling
    if curr_hist < prev_hist:
        return 30.0

    return 50.0


def score_ema(df: pd.DataFrame) -> float:
    price = df["close"].iloc[-1]
    ema_s = df["ema_short"].iloc[-1]
    ema_l = df["ema_long"].iloc[-1]

    if pd.isna(ema_s) or pd.isna(ema_l):
        return 50.0

    # Strong uptrend: price > short EMA > long EMA
    if price > ema_s > ema_l:
        return 100.0
    # Price above long EMA but below short (pullback in uptrend)
    if price > ema_l and price < ema_s and ema_s > ema_l:
        return 75.0
    # Golden cross territory but price dipping
    if ema_s > ema_l and price < ema_l:
        return 40.0
    # Death cross: short < long
    if ema_s < ema_l:
        return 20.0

    return 50.0


def score_bollinger(df: pd.DataFrame) -> float:
    bb_pct = df["bb_pct"].iloc[-1]
    ema_s = df["ema_short"].iloc[-1]
    ema_l = df["ema_long"].iloc[-1]

    if pd.isna(bb_pct):
        return 50.0

    in_uptrend = not pd.isna(ema_s) and not pd.isna(ema_l) and ema_s > ema_l

    # Near lower band in an uptrend = good buy
    if bb_pct < 0.2 and in_uptrend:
        return 100.0
    if bb_pct < 0.2:
        return 60.0
    if 0.2 <= bb_pct <= 0.5:
        return 70.0
    if bb_pct > 0.95:
        return 15.0

    return 50.0


def score_volume(df: pd.DataFrame, params: dict) -> float:
    ratio = df["vol_ratio"].iloc[-1]
    if pd.isna(ratio):
        return 50.0

    spike = params["volume"]["spike_multiplier"]
    price_up = df["close"].iloc[-1] > df["close"].iloc[-2] if len(df) >= 2 else False

    # High volume + price up = conviction
    if ratio >= spike and price_up:
        return 100.0
    if ratio >= spike:
        return 60.0
    if ratio >= 1.0 and price_up:
        return 70.0
    if ratio < 0.5:
        return 30.0

    return 50.0


def score_adx(df: pd.DataFrame, params: dict) -> float:
    adx_val = df["adx"].iloc[-1]
    if pd.isna(adx_val):
        return 50.0

    threshold = params["adx"]["strong_trend"]

    if adx_val >= threshold:
        return min(100, 60 + (adx_val - threshold) * 2)
    return max(20, 60 - (threshold - adx_val) * 2)


def score_support_resistance(df: pd.DataFrame, params: dict) -> float:
    supports, resistances = find_support_resistance(df, params["support_resistance"]["lookback"])
    price = df["close"].iloc[-1]
    proximity = params["support_resistance"]["proximity_pct"]

    if not supports and not resistances:
        return 50.0

    # Near support = bullish, near resistance = bearish
    near_support = any(abs(price - s) / price <= proximity for s in supports) if supports else False
    near_resistance = any(abs(price - r) / price <= proximity for r in resistances) if resistances else False

    if near_support and not near_resistance:
        return 90.0
    if near_support and near_resistance:
        return 50.0
    if near_resistance:
        return 20.0

    # Between levels — proportional score based on distance to support vs resistance
    if supports and resistances:
        nearest_sup = max(s for s in supports if s < price) if any(s < price for s in supports) else min(supports)
        nearest_res = min(r for r in resistances if r > price) if any(r > price for r in resistances) else max(resistances)
        total_range = nearest_res - nearest_sup
        if total_range > 0:
            pct_from_support = (price - nearest_sup) / total_range
            return max(20, 90 - pct_from_support * 70)

    return 50.0


def compute_technical_score(df: pd.DataFrame) -> dict:
    """Compute the composite technical score (0-100) for a stock."""
    if df.empty or len(df) < 50:
        return {"score": 0, "details": {}, "valid": False}

    df = compute_indicators(df)
    p = _load_params()

    scores = {
        "rsi": score_rsi(df, p),
        "macd": score_macd(df),
        "ema": score_ema(df),
        "bollinger": score_bollinger(df),
        "volume": score_volume(df, p),
        "adx": score_adx(df, p),
        "support_resistance": score_support_resistance(df, p),
    }

    weights = {
        "rsi": p["rsi"]["weight"],
        "macd": p["macd"]["weight"],
        "ema": p["ema"]["weight"],
        "bollinger": p["bollinger"]["weight"],
        "volume": p["volume"]["weight"],
        "adx": p["adx"]["weight"],
        "support_resistance": p["support_resistance"]["weight"],
    }

    composite = sum(scores[k] * weights[k] for k in scores) / sum(weights.values())

    return {
        "score": round(composite, 2),
        "details": {k: round(v, 2) for k, v in scores.items()},
        "valid": True,
        "indicators": {
            "rsi": round(df["rsi"].iloc[-1], 2) if not pd.isna(df["rsi"].iloc[-1]) else None,
            "macd_hist": round(df["macd_hist"].iloc[-1], 4) if not pd.isna(df["macd_hist"].iloc[-1]) else None,
            "adx": round(df["adx"].iloc[-1], 2) if not pd.isna(df["adx"].iloc[-1]) else None,
            "atr": round(df["atr"].iloc[-1], 4) if not pd.isna(df["atr"].iloc[-1]) else None,
            "bb_pct": round(df["bb_pct"].iloc[-1], 4) if not pd.isna(df["bb_pct"].iloc[-1]) else None,
            "vol_ratio": round(df["vol_ratio"].iloc[-1], 2) if not pd.isna(df["vol_ratio"].iloc[-1]) else None,
        },
    }
