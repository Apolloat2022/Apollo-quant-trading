"""
Multi-Channel Alert System
Telegram, Email, SMS (Twilio), Webhook, and Console alerts.
"""

import logging
import os
import smtplib
import time
from email.mime.text import MIMEText
from typing import Optional
import requests

logger = logging.getLogger(__name__)

SIGNAL_EMOJI = {"BUY": "🟢", "SELL": "🔴", "HOLD": "🟡"}


def _format_alert(signal: dict, pos_size: Optional[dict] = None) -> str:
    """
    Format a signal dict into a rich alert message.

    Args:
        signal:   Signal dict (symbol, signal, confidence, strategy, price, details)
        pos_size: Optional position sizing dict

    Returns:
        Formatted string with emojis.
    """
    emoji  = SIGNAL_EMOJI.get(signal.get("signal", "HOLD"), "⚪")
    sym    = signal.get("symbol", "?")
    sig    = signal.get("signal", "HOLD")
    price  = signal.get("price", 0)
    conf   = signal.get("confidence", 0)
    strat  = signal.get("strategy", "?")

    # SELL signal note
    cash_note = ""
    if sig == "SELL":
        cash_note = "\n   📋 SELL: Exit long position OR short via Robinhood Margin"

    # Confidence warning
    conf_note = ""
    if conf < 0.60:
        conf_note = "\n   ⚠️  LOW CONFIDENCE: Consider skipping (<60%)"

    lines = [
        f"{emoji} *{sig}* – {sym}",
        f"   Strategy  : {strat}",
        f"   Price     : {price:.6g}",
        f"   Confidence: {conf:.1%}",
    ]

    if cash_note:
        lines.append(cash_note)
    if conf_note:
        lines.append(conf_note)

    if pos_size and sig == "BUY":
        lines += [
            f"   Qty       : {pos_size.get('quantity', 0):.4f}",
            f"   Stop Loss : {pos_size.get('stop_loss', 0):.6g}",
            f"   Take Profit: {pos_size.get('take_profit', 0):.6g}",
            f"   Risk $    : ${pos_size.get('risk_amount', 0):.2f}",
        ]

    return "\n".join(lines)


def _batch_format(signals: list[dict]) -> str:
    """Format multiple signals into one message."""
    parts = [_format_alert(s) for s in signals]
    header = f"📊 *Quant Scanner – {len(signals)} Signal(s)*\n{'─'*30}"
    return header + "\n\n" + "\n\n".join(parts)


# ──────────────────────────────────────────────────────────
# CHANNELS
# ──────────────────────────────────────────────────────────

def send_console(signal: dict, pos_size: Optional[dict] = None) -> bool:
    """Print alert to console."""
    msg = _format_alert(signal, pos_size)
    print("\n" + msg + "\n")
    return True


def send_telegram(
    signal: dict,
    pos_size: Optional[dict] = None,
    retries: int = 3,
) -> bool:
    """
    Send Telegram message via Bot API.

    Reads TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID from environment.
    """
    token   = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

    if not token or not chat_id:
        logger.warning("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not configured.")
        return False

    text = _format_alert(signal, pos_size)
    url  = f"https://api.telegram.org/bot{token}/sendMessage"

    for attempt in range(retries):
        try:
            resp = requests.post(
                url,
                json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
                timeout=10,
            )
            if resp.status_code == 200:
                logger.info(f"Telegram alert sent for {signal.get('symbol')}")
                return True
            logger.warning(f"Telegram API error {resp.status_code}: {resp.text}")
        except Exception as exc:
            logger.warning(f"Telegram attempt {attempt+1} failed: {exc}")
        if attempt < retries - 1:
            time.sleep(2 ** attempt)
    return False


def send_email(
    signal: dict,
    pos_size: Optional[dict] = None,
) -> bool:
    """
    Send email alert via SMTP.

    Reads EMAIL_FROM, EMAIL_PASSWORD, EMAIL_TO, SMTP_HOST, SMTP_PORT from env.
    """
    email_from = os.getenv("EMAIL_FROM", "")
    password   = os.getenv("EMAIL_PASSWORD", "")
    email_to   = os.getenv("EMAIL_TO", "")
    smtp_host  = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port  = int(os.getenv("SMTP_PORT", "587"))

    if not all([email_from, password, email_to]):
        logger.warning("Email credentials not fully configured.")
        return False

    text = _format_alert(signal, pos_size).replace("*", "")
    sym  = signal.get("symbol", "?")
    sig  = signal.get("signal", "?")

    msg = MIMEText(text)
    msg["Subject"] = f"[Quant Alert] {sig} – {sym}"
    msg["From"]    = email_from
    msg["To"]      = email_to

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(email_from, password)
            server.sendmail(email_from, [email_to], msg.as_string())
        logger.info(f"Email alert sent for {sym}")
        return True
    except Exception as exc:
        logger.error(f"Email send failed: {exc}")
        return False


def send_sms(signal: dict, pos_size: Optional[dict] = None) -> bool:
    """
    Send SMS via Twilio.

    Reads TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER, TWILIO_TO_NUMBER from env.
    """
    account_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
    auth_token  = os.getenv("TWILIO_AUTH_TOKEN", "")
    from_num    = os.getenv("TWILIO_FROM_NUMBER", "")
    to_num      = os.getenv("TWILIO_TO_NUMBER", "")

    if not all([account_sid, auth_token, from_num, to_num]):
        logger.warning("Twilio credentials not fully configured.")
        return False

    try:
        from twilio.rest import Client
        client = Client(account_sid, auth_token)
        text   = _format_alert(signal, pos_size).replace("*", "").replace("_", "")
        client.messages.create(body=text[:160], from_=from_num, to=to_num)
        logger.info(f"SMS alert sent for {signal.get('symbol')}")
        return True
    except ImportError:
        logger.error("twilio not installed. Run: pip install twilio")
        return False
    except Exception as exc:
        logger.error(f"SMS send failed: {exc}")
        return False


def send_webhook(signal: dict, pos_size: Optional[dict] = None) -> bool:
    """
    Send signal payload to a webhook URL.

    Reads WEBHOOK_URL from environment.
    """
    webhook_url = os.getenv("WEBHOOK_URL", "")
    if not webhook_url:
        logger.warning("WEBHOOK_URL not configured.")
        return False

    payload = {**signal}
    if pos_size:
        payload["position"] = pos_size

    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        if resp.status_code in (200, 201, 204):
            logger.info(f"Webhook alert sent for {signal.get('symbol')}")
            return True
        logger.warning(f"Webhook error {resp.status_code}")
        return False
    except Exception as exc:
        logger.error(f"Webhook send failed: {exc}")
        return False


# ──────────────────────────────────────────────────────────
# UNIFIED DISPATCHER
# ──────────────────────────────────────────────────────────

CHANNEL_MAP = {
    "console":  send_console,
    "telegram": send_telegram,
    "email":    send_email,
    "sms":      send_sms,
    "webhook":  send_webhook,
}


def dispatch_alerts(
    signals: list[dict],
    channels: list[str],
    pos_sizes: Optional[dict] = None,
) -> dict:
    """
    Send alerts for a list of signals across requested channels.

    Args:
        signals:   List of signal dicts
        channels:  Channel names to use e.g. ['console', 'telegram']
        pos_sizes: Optional mapping of symbol -> position size dict

    Returns:
        Dict of channel -> success count.
    """
    if not signals:
        return {}

    results: dict = {ch: 0 for ch in channels}

    for signal in signals:
        sym = signal.get("symbol")
        pos = (pos_sizes or {}).get(sym)

        for ch in channels:
            fn = CHANNEL_MAP.get(ch)
            if fn is None:
                logger.warning(f"Unknown alert channel: {ch}")
                continue
            if fn(signal, pos):
                results[ch] += 1

    return results
