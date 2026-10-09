"""Alert delivery: console always, Telegram when a bot token and chat id are configured."""
from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request

from .signals import Signal

log = logging.getLogger("tradekit.alerts")

SETUP_HE = {
    "orb": "פריצת טווח פתיחה", "vwap_pullback": "פולבק ל-VWAP", "gap_and_go": "גאפ אנד גו",
    "earnings_gap": "גאפ דוחות", "trend_pullback": "פולבק במגמה", "base_breakout": "פריצת בסיס",
    "rsi2_reversion": "RSI(2) היפוך",
}


def fmt(v: float) -> str:
    return f"{v:,.4f}" if v < 1 else f"{v:,.2f}"


def render(sig: Signal, prob: float | None, shares: int | None) -> str:
    side = "LONG 🟢" if sig.side > 0 else "SHORT 🔴"
    pct = (sig.target / sig.entry - 1) * 100
    lines = [
        f"<b>{sig.symbol}</b> · {side} · {SETUP_HE.get(sig.setup, sig.setup)} ({'יומי' if sig.horizon == 'intraday' else 'סווינג'})",
        f"כניסה {fmt(sig.entry)} | סטופ {fmt(sig.stop)} | TP {fmt(sig.take_profit or sig.target)} | יעד {fmt(sig.target)} ({pct:+.1f}%)",
        f"סיכון/סיכוי 1:{sig.reward_r:.1f}" + (f" · הסתברות {prob:.0%}" if prob is not None and prob == prob else "")
        + (f" · {shares} מניות" if shares else ""),
    ]
    if sig.note:
        lines.append(sig.note)
    return "\n".join(lines)


class Notifier:
    def __init__(self, telegram_token: str | None = None, telegram_chat: str | None = None):
        self.token, self.chat = telegram_token, telegram_chat

    def send(self, text: str) -> None:
        print("\n" + text.replace("<b>", "").replace("</b>", "") + "\n", flush=True)
        if not (self.token and self.chat):
            return
        data = urllib.parse.urlencode({"chat_id": self.chat, "text": text, "parse_mode": "HTML"}).encode()
        try:
            with urllib.request.urlopen(f"https://api.telegram.org/bot{self.token}/sendMessage", data, timeout=10) as r:
                if json.load(r).get("ok") is not True:
                    log.warning("telegram rejected the message")
        except Exception as e:  # never let a notification failure stop the scanner
            log.warning("telegram send failed: %s", e)
