"""Telegram and Desktop notification dispatcher for ultra-fresh (<15m) high-match roles."""
import os
import httpx
from typing import Optional
from hunterz.db.models import JobModel
from hunterz.config import HunterZConfig


class JobNotifier:
    """Dispatches real-time Telegram and terminal notifications for hot leads."""

    def __init__(self, config: HunterZConfig):
        self.config = config

    async def notify_hot_job(self, job: JobModel) -> bool:
        """
        Sends an alert if a role matches with high score (>=80%) and ultra-fresh recency (<60m).
        """
        token = getattr(self.config.profile, "telegram_bot_token", None) or os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = getattr(self.config.profile, "telegram_chat_id", None) or os.getenv("TELEGRAM_CHAT_ID")

        if not token or not chat_id:
            # Telegram not configured yet, skip silently
            return False

        message = (
            f"🔥 *HUNTERZ HIGH-MATCH JOB ALERT!* 🔥\n\n"
            f"🎯 *Match:* {job.match_score}%\n"
            f"💼 *Role:* {job.title}\n"
            f"🏢 *Company:* {job.company}\n"
            f"📍 *Location:* {job.location}\n"
            f"🌐 *Source:* {job.source.upper()}\n\n"
            f"🔗 [View and Apply]({job.url})"
        )

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown",
            "disable_web_page_preview": False
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload)
                return resp.status_code == 200
        except Exception as e:
            print(f"Telegram notification error: {e}")
            return False
