from collections import Counter

from config.loader import get_config
from data.fetcher import ticker_to_sector


def build_portfolio(
    scored_stocks: list[dict],
    regime_data: dict,
) -> list[dict]:
    """
    Select top stocks and assign position sizes.

    scored_stocks: list of dicts with keys: ticker, composite, sector, price, atr, ...
    regime_data: output of detect_regime()

    Returns ordered list of portfolio entries.
    """
    params = get_config()
    capital = params["capital"]["total"]
    max_positions = params["capital"]["max_positions"]
    max_sector = params["capital"]["max_sector_exposure"]
    min_score = params["scoring"]["min_score_threshold"]

    allocation_pct = regime_data["allocation_pct"]
    available_capital = capital * allocation_pct

    candidates = [s for s in scored_stocks if s["composite"] >= min_score]
    candidates.sort(key=lambda x: x["composite"], reverse=True)

    # Apply sector cap
    sector_count: Counter = Counter()
    sector_map = ticker_to_sector()
    selected: list[dict] = []

    for stock in candidates:
        if len(selected) >= max_positions:
            break

        sector = sector_map.get(stock["ticker"], stock.get("sector", "unknown"))
        if sector_count[sector] >= max_sector:
            continue

        sector_count[sector] += 1
        selected.append({**stock, "sector": sector})

    if not selected:
        return []

    # Position sizing: ATR-based volatility weighting
    # Lower volatility → larger position (inverse vol weighting)
    inv_vols = []
    for s in selected:
        atr = s.get("atr")
        price = s.get("price", 1)
        if atr and price and atr > 0:
            atr_pct = atr / price
            inv_vols.append(1.0 / atr_pct)
        else:
            inv_vols.append(1.0)

    total_inv_vol = sum(inv_vols)
    if total_inv_vol == 0:
        total_inv_vol = len(selected)
        inv_vols = [1.0] * len(selected)

    portfolio: list[dict] = []
    for i, stock in enumerate(selected):
        weight = inv_vols[i] / total_inv_vol
        position_size = round(available_capital * weight, 2)

        price = stock.get("price", 0)
        shares = round(position_size / price, 6) if price > 0 else 0

        portfolio.append({
            "rank": i + 1,
            "ticker": stock["ticker"],
            "name": stock.get("name", stock["ticker"]),
            "sector": stock["sector"],
            "composite_score": stock["composite"],
            "technical_score": stock.get("technical", 0),
            "fundamental_score": stock.get("fundamental", 0),
            "price": price,
            "position_usd": position_size,
            "shares": shares,
            "weight_pct": round(weight * 100, 1),
            "atr": stock.get("atr"),
        })

    return portfolio
