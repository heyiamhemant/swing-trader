from config.loader import get_config


def _load_weights() -> dict:
    return get_config()["scoring"]


def compute_composite_score(
    technical_result: dict,
    fundamental_result: dict,
    macro_score: float,
) -> dict:
    """
    Combine technical, fundamental, and macro scores into a single composite.

    Returns dict with composite score and breakdown.
    """
    w = _load_weights()

    tech_score = technical_result.get("score", 0) if technical_result.get("valid") else 0
    fund_score = fundamental_result.get("score", 0) if fundamental_result.get("valid") else 0

    composite = (
        w["weights"]["technical"] * tech_score
        + w["weights"]["fundamental"] * fund_score
        + w["weights"]["macro"] * macro_score
    )

    return {
        "composite": round(composite, 2),
        "technical": round(tech_score, 2),
        "fundamental": round(fund_score, 2),
        "macro": round(macro_score, 2),
        "weights": w["weights"],
    }
