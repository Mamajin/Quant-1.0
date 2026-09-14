"""Alert channels (manual FR-008: 'push notifications (Telegram/Discord/
desktop) when rules fire'). Discord is not implemented (no free-tier
distinction from Telegram to justify it in this pass) -- Telegram + desktop
cover the manual's "free, reliable, mobile-friendly" pick (sec 2.9)."""
from __future__ import annotations

import logging
import os
from typing import Protocol

import requests

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org"


class Notifier(Protocol):
    name: str

    def send(self, message: str) -> bool:
        """Send `message`; return True on success."""
        ...


class TelegramNotifier:
    name = "telegram"

    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id

    @classmethod
    def from_env(cls) -> "TelegramNotifier | None":
        token = os.environ.get("TELEGRAM_BOT_TOKEN")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID")
        if not token or not chat_id:
            logger.warning("Telegram channel enabled but TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID not set in .env")
            return None
        return cls(token, chat_id)

    def send(self, message: str) -> bool:
        try:
            resp = requests.post(
                f"{TELEGRAM_API_BASE}/bot{self.bot_token}/sendMessage",
                data={"chat_id": self.chat_id, "text": message},
                timeout=10,
            )
            if not resp.ok:
                logger.warning("Telegram send failed: %s %s", resp.status_code, resp.text)
            return resp.ok
        except requests.RequestException as exc:
            logger.warning("Telegram send failed: %s", exc)
            return False


class DesktopNotifier:
    name = "desktop"

    def send(self, message: str) -> bool:
        try:
            from plyer import notification
            notification.notify(title="Quantify Alert", message=message[:250], timeout=10)
            return True
        except Exception as exc:  # noqa: BLE001 - plyer backends vary a lot by OS
            logger.warning("Desktop notification failed: %s", exc)
            return False


def build_notifiers(channel_names: list[str]) -> list[Notifier]:
    notifiers: list[Notifier] = []
    for name in channel_names:
        if name == "telegram":
            telegram = TelegramNotifier.from_env()
            if telegram:
                notifiers.append(telegram)
        elif name == "desktop":
            notifiers.append(DesktopNotifier())
        else:
            logger.warning("Unknown alert channel %r, skipping", name)
    return notifiers
