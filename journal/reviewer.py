from datetime import datetime

from config.loader import get_config
from journal import tracker
from data.fetcher import fetch_price_data


def current_quarter() -> str:
    now = datetime.now()
    q = (now.month - 1) // 3 + 1
    return f"{now.year}Q{q}"


def compute_quarterly_review(quarter: str | None = None) -> dict:
    """
    Analyze closed trades for a given quarter and produce performance metrics.
    """
    quarter = quarter or current_quarter()
    trades = tracker.get_closed_trades(quarter)

    if not trades:
        return {
            "quarter": quarter,
            "total_trades": 0,
            "message": "No closed trades found for this quarter.",
        }

    total_pnl = sum(t["pnl"] or 0 for t in trades)
    winners = [t for t in trades if (t["pnl"] or 0) > 0]
    losers = [t for t in trades if (t["pnl"] or 0) <= 0]
    win_rate = len(winners) / len(trades) * 100 if trades else 0

    avg_win = sum(t["pnl"] for t in winners) / len(winners) if winners else 0
    avg_loss = sum(abs(t["pnl"]) for t in losers) / len(losers) if losers else 0
    avg_rr = avg_win / avg_loss if avg_loss > 0 else float("inf")

    best = max(trades, key=lambda t: t["pnl"] or 0) if trades else None
    worst = min(trades, key=lambda t: t["pnl"] or 0) if trades else None

    # SPY benchmark return for the quarter
    spy_return = _spy_quarter_return(quarter)

    total_capital = get_config()["capital"]["total"]
    total_pnl_pct = (total_pnl / total_capital) * 100

    alpha = total_pnl_pct - spy_return if spy_return is not None else None

    # Sector breakdown
    sector_pnl: dict[str, float] = {}
    for t in trades:
        sec = t.get("sector", "unknown")
        sector_pnl[sec] = sector_pnl.get(sec, 0) + (t["pnl"] or 0)

    # Indicator effectiveness (by score — did higher-scored trades win more?)
    high_score_trades = [t for t in trades if (t.get("composite_score") or 0) >= 65]
    low_score_trades = [t for t in trades if (t.get("composite_score") or 0) < 65]
    high_score_wr = (
        sum(1 for t in high_score_trades if (t["pnl"] or 0) > 0) / len(high_score_trades) * 100
        if high_score_trades else 0
    )
    low_score_wr = (
        sum(1 for t in low_score_trades if (t["pnl"] or 0) > 0) / len(low_score_trades) * 100
        if low_score_trades else 0
    )

    result = {
        "quarter": quarter,
        "total_trades": len(trades),
        "winning_trades": len(winners),
        "losing_trades": len(losers),
        "win_rate": round(win_rate, 1),
        "total_pnl": round(total_pnl, 2),
        "total_pnl_pct": round(total_pnl_pct, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "avg_rr": round(avg_rr, 2),
        "best_trade": f"{best['ticker']} +${best['pnl']:.2f}" if best else "N/A",
        "worst_trade": f"{worst['ticker']} ${worst['pnl']:.2f}" if worst else "N/A",
        "spy_return_pct": round(spy_return, 2) if spy_return is not None else None,
        "alpha": round(alpha, 2) if alpha is not None else None,
        "sector_pnl": sector_pnl,
        "high_score_win_rate": round(high_score_wr, 1),
        "low_score_win_rate": round(low_score_wr, 1),
        "improvement_hints": _generate_hints(
            win_rate, avg_rr, sector_pnl, high_score_wr, low_score_wr, alpha
        ),
    }

    tracker.save_quarterly_review(result)
    return result


def _spy_quarter_return(quarter: str) -> float | None:
    try:
        year, q = quarter.split("Q")
        q_num = int(q)
        start_month = (q_num - 1) * 3 + 1

        df = fetch_price_data("SPY", days=120)
        if df.empty:
            return None

        q_start = f"{year}-{start_month:02d}-01"
        q_data = df[df.index >= q_start]
        if len(q_data) < 2:
            return None

        return ((q_data["close"].iloc[-1] / q_data["close"].iloc[0]) - 1) * 100
    except Exception:
        return None


def _generate_hints(
    win_rate: float,
    avg_rr: float,
    sector_pnl: dict,
    high_score_wr: float,
    low_score_wr: float,
    alpha: float | None,
) -> list[str]:
    hints = []

    if win_rate < 50:
        hints.append(
            f"Win rate is {win_rate:.0f}% — consider tightening entry criteria "
            "(raise min_score_threshold in strategy_params.yaml)."
        )
    if avg_rr < 1.5:
        hints.append(
            f"Average R:R is {avg_rr:.1f}x — consider widening targets or tightening stops."
        )
    if alpha is not None and alpha < 0:
        hints.append(
            f"Strategy underperformed SPY by {abs(alpha):.1f}% — review sector allocation."
        )

    worst_sectors = sorted(sector_pnl.items(), key=lambda x: x[1])
    if worst_sectors and worst_sectors[0][1] < 0:
        hints.append(
            f"Worst sector: {worst_sectors[0][0]} (${worst_sectors[0][1]:.2f}) — "
            "consider reducing exposure or removing tickers."
        )

    if high_score_wr > low_score_wr + 15:
        hints.append(
            "High-conviction trades significantly outperform — "
            "raise the minimum score threshold for entries."
        )
    elif low_score_wr > high_score_wr + 10:
        hints.append(
            "Lower-scored trades are doing well — scoring model may need recalibration. "
            "Review indicator weights."
        )

    if not hints:
        hints.append("Strategy is performing well. Maintain current parameters.")

    return hints
