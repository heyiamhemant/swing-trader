"""
Notification helpers: Telegram bot and email alerts.
"""

import os
import json
import smtplib
from email.mime.text import MIMEText
from pathlib import Path

import requests


def send_telegram(message: str, parse_mode: str = "Markdown") -> bool:
    """
    Send a Telegram message. Requires env vars:
      TELEGRAM_BOT_TOKEN
      TELEGRAM_CHAT_ID
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False

    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        resp = requests.post(url, json={
            "chat_id": chat_id,
            "text": message,
            "parse_mode": parse_mode,
        }, timeout=10)
        return resp.status_code == 200
    except Exception:
        return False


def send_email(subject: str, body: str) -> bool:
    """
    Send an email alert. Requires env vars:
      SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, ALERT_EMAIL_TO
    """
    host = os.environ.get("SMTP_HOST")
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER")
    passwd = os.environ.get("SMTP_PASS")
    to_addr = os.environ.get("ALERT_EMAIL_TO")

    if not all([host, user, passwd, to_addr]):
        return False

    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = user
        msg["To"] = to_addr

        with smtplib.SMTP(host, port) as server:
            server.starttls()
            server.login(user, passwd)
            server.sendmail(user, [to_addr], msg.as_string())
        return True
    except Exception:
        return False


def format_decision_alert(decision: dict) -> str:
    """Format Claude's decision into a notification-friendly message."""
    lines = []
    lines.append("*Swing Trader — New Signals*\n")

    if decision.get("analysis_summary"):
        lines.append(f"_{decision['analysis_summary']}_\n")

    picks = decision.get("picks", [])
    if picks:
        lines.append(f"*{len(picks)} picks:*")
        for p in picks:
            action = p.get("action", "BUY")
            ticker = p.get("ticker", "?")
            entry = p.get("entry_price", 0)
            stop = p.get("stop_loss", 0)
            target = p.get("target", 0)
            size = p.get("position_usd", 0)
            lines.append(
                f"  {action} {ticker} @ ${entry:.2f} | "
                f"Stop ${stop:.2f} | Target ${target:.2f} | ${size:.0f}"
            )

    alloc = decision.get("portfolio_allocation", {})
    if alloc:
        lines.append(f"\nDeployed: ${alloc.get('total_deployed', 0):.0f} | Cash: ${alloc.get('cash_reserve', 0):.0f}")

    warnings = decision.get("risk_warnings", [])
    if warnings:
        lines.append(f"\n⚠ {warnings[0]}")

    return "\n".join(lines)


def notify_decision(decision: dict) -> None:
    """Send the decision via all configured channels."""
    msg = format_decision_alert(decision)
    send_telegram(msg)
    send_email("Swing Trader Signal", msg.replace("*", "").replace("_", ""))
