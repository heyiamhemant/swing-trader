from config.loader import get_config
from analysis.technical import find_support_resistance


def _load_params() -> dict:
    return get_config()["risk"]


def compute_levels(
    price: float,
    atr: float | None,
    price_df=None,
) -> dict:
    """
    Compute stop loss, target, and trailing stop for a given entry price.

    Uses the best of ATR-based, support/resistance-based, and hard-floor levels.
    """
    p = _load_params()
    atr = atr or price * 0.02  # fallback: 2% of price

    # --- Stop Loss ---
    atr_stop = price - p["stop_loss"]["atr_multiplier"] * atr
    hard_floor = price * (1 - p["stop_loss"]["hard_floor_pct"])

    # Support-based stop
    support_stop = None
    if price_df is not None and not price_df.empty:
        supports, _ = find_support_resistance(price_df)
        below = [s for s in supports if s < price]
        if below:
            support_stop = max(below) * 0.995  # just below support

    stop_candidates = [atr_stop, hard_floor]
    if support_stop is not None:
        stop_candidates.append(support_stop)

    # Use the highest (least loss) stop that's still below price
    stop_loss = max(s for s in stop_candidates if s < price) if any(s < price for s in stop_candidates) else hard_floor

    # --- Target ---
    atr_target = price + p["target"]["atr_multiplier"] * atr
    risk = price - stop_loss
    min_rr_target = price + risk * p["target"]["min_rr_ratio"]

    resistance_target = None
    if price_df is not None and not price_df.empty:
        _, resistances = find_support_resistance(price_df)
        above = [r for r in resistances if r > price]
        if above:
            resistance_target = min(above)

    target_candidates = [atr_target, min_rr_target]
    if resistance_target is not None:
        target_candidates.append(resistance_target)

    target = max(t for t in target_candidates if t > price) if any(t > price for t in target_candidates) else atr_target

    # --- Risk/Reward ---
    risk_amt = price - stop_loss
    reward_amt = target - price
    rr_ratio = round(reward_amt / risk_amt, 2) if risk_amt > 0 else 0

    # --- Trailing Stop ---
    trailing = {
        "activation_pct": p["trailing_stop"]["activation_pct"],
        "activation_price": round(price * (1 + p["trailing_stop"]["activation_pct"]), 2),
        "trail_atr_mult": p["trailing_stop"]["atr_multiplier"],
    }

    return {
        "entry": round(price, 2),
        "stop_loss": round(stop_loss, 2),
        "target": round(target, 2),
        "risk_pct": round((risk_amt / price) * 100, 2),
        "reward_pct": round((reward_amt / price) * 100, 2),
        "rr_ratio": rr_ratio,
        "trailing_stop": trailing,
    }
