from config.loader import get_config, get_etf_tickers


def _safe(val, default=None):
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def score_pe(data: dict, params: dict) -> float:
    pe = _safe(data.get("pe_forward")) or _safe(data.get("pe_trailing"))
    if pe is None or pe <= 0:
        return 40.0  # Can't evaluate — neutral-low

    max_pe = params["pe_ratio"]["max_acceptable"]

    if pe < 15:
        return 90.0
    if pe < 25:
        return 75.0
    if pe < max_pe:
        return 55.0
    return max(10, 40 - (pe - max_pe))


def score_revenue_growth(data: dict, params: dict) -> float:
    growth = _safe(data.get("revenue_growth"))
    if growth is None:
        return 40.0

    min_g = params["revenue_growth"]["min_yoy"]

    if growth >= min_g * 3:
        return 100.0
    if growth >= min_g * 2:
        return 90.0
    if growth >= min_g:
        return 75.0
    if growth >= 0:
        return 50.0
    return max(5, 30 + growth * 100)


def score_eps_growth(data: dict, params: dict) -> float:
    growth = _safe(data.get("earnings_growth"))
    if growth is None:
        return 40.0

    min_g = params["eps_growth"]["min_yoy"]

    if growth >= min_g * 4:
        return 100.0
    if growth >= min_g * 2:
        return 85.0
    if growth >= min_g:
        return 70.0
    if growth >= 0:
        return 50.0
    return max(5, 30 + growth * 100)


def score_debt_to_equity(data: dict, params: dict) -> float:
    de = _safe(data.get("debt_to_equity"))
    if de is None:
        return 50.0

    # yfinance debtToEquity is consistently in percentage form (150 = 1.5x)
    de_ratio = de / 100.0
    max_de = params["debt_to_equity"]["max_acceptable"]

    if de_ratio < 0.3:
        return 95.0
    if de_ratio < 0.7:
        return 80.0
    if de_ratio < max_de:
        return 60.0
    return max(10, 50 - (de_ratio - max_de) * 20)


def score_roe(data: dict, params: dict) -> float:
    roe = _safe(data.get("return_on_equity"))
    if roe is None:
        return 40.0

    # yfinance sometimes returns ROE as percentage (e.g. 25 = 0.25)
    if abs(roe) > 1:
        roe = roe / 100.0

    min_roe = params["roe"]["min_acceptable"]

    if roe >= min_roe * 2:
        return 100.0
    if roe >= min_roe:
        return 80.0
    if roe >= min_roe * 0.5:
        return 55.0
    if roe >= 0:
        return 35.0
    return 10.0


def score_free_cash_flow(data: dict) -> float:
    fcf = _safe(data.get("free_cash_flow"))
    if fcf is None:
        return 40.0

    if fcf > 0:
        # Positive FCF — scale by magnitude relative to market cap
        mcap = _safe(data.get("market_cap"))
        if mcap and mcap > 0:
            fcf_yield = fcf / mcap
            if fcf_yield > 0.08:
                return 100.0
            if fcf_yield > 0.04:
                return 80.0
            return 65.0
        return 70.0

    return 20.0


def compute_fundamental_score(data: dict) -> dict:
    """Compute composite fundamental score (0-100) for a stock."""
    if not data or not data.get("ticker"):
        return {"score": 0, "details": {}, "valid": False}

    p = get_config()["fundamental"]

    is_etf = data["ticker"] in get_etf_tickers()
    if is_etf:
        return {"score": 50, "details": {"note": "ETF — fundamentals not applicable"}, "valid": True}

    scores = {
        "pe": score_pe(data, p),
        "revenue_growth": score_revenue_growth(data, p),
        "eps_growth": score_eps_growth(data, p),
        "debt_to_equity": score_debt_to_equity(data, p),
        "roe": score_roe(data, p),
        "fcf": score_free_cash_flow(data),
    }

    weights = {
        "pe": p["pe_ratio"]["weight"],
        "revenue_growth": p["revenue_growth"]["weight"],
        "eps_growth": p["eps_growth"]["weight"],
        "debt_to_equity": p["debt_to_equity"]["weight"],
        "roe": p["roe"]["weight"],
        "fcf": p["free_cash_flow"]["weight"],
    }

    composite = sum(scores[k] * weights[k] for k in scores) / sum(weights.values())

    return {
        "score": round(composite, 2),
        "details": {k: round(v, 2) for k, v in scores.items()},
        "valid": True,
        "fundamentals": {
            "pe": _safe(data.get("pe_forward")) or _safe(data.get("pe_trailing")),
            "revenue_growth": _safe(data.get("revenue_growth")),
            "earnings_growth": _safe(data.get("earnings_growth")),
            "debt_to_equity": _safe(data.get("debt_to_equity")),
            "roe": _safe(data.get("return_on_equity")),
            "fcf": _safe(data.get("free_cash_flow")),
            "market_cap": _safe(data.get("market_cap")),
        },
    }
