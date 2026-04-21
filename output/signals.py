import json
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box

console = Console()


def display_regime(regime_data: dict) -> None:
    regime = regime_data["regime"].upper()
    color = {"BULL": "green", "NEUTRAL": "yellow", "BEAR": "red"}.get(regime, "white")

    panel_text = Text()
    panel_text.append(f"Regime: ", style="bold")
    panel_text.append(f"{regime}", style=f"bold {color}")
    panel_text.append(f"  |  Allocation: {regime_data['allocation_pct']*100:.0f}%")
    panel_text.append(f"  |  Tilt: {regime_data['tilt']}")
    panel_text.append(f"\n\n")

    for name, sig in regime_data["signals"].items():
        indicator = "+" if sig["bullish"] else "-"
        sig_color = "green" if sig["bullish"] else "red"
        panel_text.append(f"  [{indicator}] ", style=f"bold {sig_color}")
        panel_text.append(f"{name}: {sig['detail']}\n")

    console.print(Panel(panel_text, title="Macro Regime", border_style=color))


def display_scan_results(portfolio: list[dict], risk_levels: dict[str, dict]) -> None:
    if not portfolio:
        console.print("[yellow]No stocks met the minimum score threshold.[/yellow]")
        return

    table = Table(
        title="Trade Signals",
        box=box.ROUNDED,
        show_lines=True,
        title_style="bold cyan",
    )

    table.add_column("#", style="dim", width=3)
    table.add_column("Ticker", style="bold white", width=7)
    table.add_column("Sector", width=18)
    table.add_column("Price", justify="right", width=9)
    table.add_column("Score", justify="right", width=7)
    table.add_column("Tech", justify="right", width=6)
    table.add_column("Fund", justify="right", width=6)
    table.add_column("Size $", justify="right", width=8)
    table.add_column("Shares", justify="right", width=8)
    table.add_column("Stop", justify="right", style="red", width=9)
    table.add_column("Target", justify="right", style="green", width=9)
    table.add_column("R:R", justify="right", width=5)

    for p in portfolio:
        ticker = p["ticker"]
        risk = risk_levels.get(ticker, {})

        score_color = "green" if p["composite_score"] >= 70 else "yellow" if p["composite_score"] >= 55 else "red"

        table.add_row(
            str(p["rank"]),
            ticker,
            p.get("sector", ""),
            f"${p['price']:.2f}",
            f"[{score_color}]{p['composite_score']:.1f}[/{score_color}]",
            f"{p['technical_score']:.0f}",
            f"{p['fundamental_score']:.0f}",
            f"${p['position_usd']:.0f}",
            f"{p['shares']:.4f}",
            f"${risk.get('stop_loss', 0):.2f}",
            f"${risk.get('target', 0):.2f}",
            f"{risk.get('rr_ratio', 0):.1f}",
        )

    console.print(table)

    total_deployed = sum(p["position_usd"] for p in portfolio)
    console.print(f"\n  Total deployed: [bold]${total_deployed:.2f}[/bold] / $1000")
    console.print(f"  Positions: [bold]{len(portfolio)}[/bold] / 10")


def display_open_positions(positions: list[dict]) -> None:
    if not positions:
        console.print("[dim]No open positions.[/dim]")
        return

    table = Table(title="Open Positions", box=box.SIMPLE_HEAVY)
    table.add_column("Ticker", style="bold")
    table.add_column("Entry Date")
    table.add_column("Entry $", justify="right")
    table.add_column("Shares", justify="right")
    table.add_column("Size $", justify="right")
    table.add_column("Stop", justify="right", style="red")
    table.add_column("Target", justify="right", style="green")
    table.add_column("Score", justify="right")

    for p in positions:
        table.add_row(
            p["ticker"],
            p["entry_date"],
            f"${p['entry_price']:.2f}",
            f"{p['shares']:.4f}",
            f"${p['position_usd']:.2f}",
            f"${p['stop_loss']:.2f}" if p.get("stop_loss") else "-",
            f"${p['target']:.2f}" if p.get("target") else "-",
            f"{(p.get('composite_score') or 0):.1f}",
        )

    console.print(table)


def display_journal(trades: list[dict]) -> None:
    if not trades:
        console.print("[dim]No trades in journal.[/dim]")
        return

    table = Table(title="Trade Journal", box=box.ROUNDED, show_lines=True)
    table.add_column("Ticker", style="bold")
    table.add_column("Entry", justify="right")
    table.add_column("Exit", justify="right")
    table.add_column("P&L $", justify="right")
    table.add_column("P&L %", justify="right")
    table.add_column("Reason")
    table.add_column("Status")

    for t in trades:
        pnl = t.get("pnl")
        pnl_color = "green" if pnl and pnl > 0 else "red" if pnl and pnl < 0 else "dim"
        status = "CLOSED" if t.get("exit_date") else "[bold cyan]OPEN[/bold cyan]"

        table.add_row(
            t["ticker"],
            f"${t['entry_price']:.2f} ({t['entry_date']})",
            f"${t['exit_price']:.2f} ({t['exit_date']})" if t.get("exit_date") else "-",
            f"[{pnl_color}]${pnl:.2f}[/{pnl_color}]" if pnl is not None else "-",
            f"[{pnl_color}]{t.get('pnl_pct', 0):.1f}%[/{pnl_color}]" if pnl is not None else "-",
            t.get("exit_reason", "-") or "-",
            status,
        )

    console.print(table)


def display_review(review: dict) -> None:
    if review.get("total_trades", 0) == 0:
        console.print(f"[dim]{review.get('message', 'No data.')}[/dim]")
        return

    console.print(Panel(
        f"[bold]{review['quarter']}[/bold] Performance Review",
        border_style="cyan",
    ))

    metrics = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    metrics.add_column("Metric", style="bold")
    metrics.add_column("Value", justify="right")

    pnl_color = "green" if review["total_pnl"] >= 0 else "red"

    metrics.add_row("Total Trades", str(review["total_trades"]))
    metrics.add_row("Wins / Losses", f"{review['winning_trades']} / {review['losing_trades']}")
    metrics.add_row("Win Rate", f"{review['win_rate']:.1f}%")
    metrics.add_row("Total P&L", f"[{pnl_color}]${review['total_pnl']:.2f} ({review['total_pnl_pct']:.1f}%)[/{pnl_color}]")
    metrics.add_row("Avg Win / Avg Loss", f"${review['avg_win']:.2f} / ${review['avg_loss']:.2f}")
    metrics.add_row("Avg R:R", f"{review['avg_rr']:.2f}x")
    metrics.add_row("Best Trade", review["best_trade"])
    metrics.add_row("Worst Trade", review["worst_trade"])

    if review.get("spy_return_pct") is not None:
        metrics.add_row("SPY Return", f"{review['spy_return_pct']:.2f}%")
    if review.get("alpha") is not None:
        alpha_color = "green" if review["alpha"] >= 0 else "red"
        metrics.add_row("Alpha vs SPY", f"[{alpha_color}]{review['alpha']:+.2f}%[/{alpha_color}]")

    metrics.add_row("High-Score WR", f"{review['high_score_win_rate']:.1f}%")
    metrics.add_row("Low-Score WR", f"{review['low_score_win_rate']:.1f}%")

    console.print(metrics)

    if review.get("improvement_hints"):
        console.print("\n[bold yellow]Improvement Hints:[/bold yellow]")
        for hint in review["improvement_hints"]:
            console.print(f"  -> {hint}")


def export_signals_json(portfolio: list[dict], risk_levels: dict, regime: dict, path: str | None = None) -> str:
    output = {
        "generated_at": datetime.now().isoformat(),
        "regime": regime,
        "signals": [],
    }

    for p in portfolio:
        ticker = p["ticker"]
        risk = risk_levels.get(ticker, {})
        output["signals"].append({
            "ticker": ticker,
            "sector": p.get("sector", ""),
            "price": p["price"],
            "composite_score": p["composite_score"],
            "technical_score": p["technical_score"],
            "fundamental_score": p["fundamental_score"],
            "position_usd": p["position_usd"],
            "shares": p["shares"],
            "stop_loss": risk.get("stop_loss"),
            "target": risk.get("target"),
            "rr_ratio": risk.get("rr_ratio"),
        })

    out_path = path or str(Path(__file__).parent.parent / "data" / "latest_signals.json")
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)

    return out_path
