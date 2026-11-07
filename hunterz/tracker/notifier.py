"""Telegram and Desktop notification dispatcher for ultra-fresh (<15m) jobs, automated applications, and pipeline events."""
import os
import re
from pathlib import Path
import httpx
from typing import Optional, List, Dict, Any
from hunterz.db.models import JobModel, ApplicationModel
from hunterz.config import HunterZConfig


class JobNotifier:
    """Dispatches real-time Telegram alerts for hot jobs, automated applications, and daemon events."""

    def __init__(self, config: HunterZConfig):
        self.config = config
        self._cached_chat_id: Optional[str] = None

    async def _get_active_chat_id(self, token: str, configured_id: Optional[str]) -> Optional[str]:
        """
        Resolve numeric chat ID. If configured with @bot_username or unset,
        queries Telegram getUpdates to auto-discover the user's personal chat ID.
        """
        if self._cached_chat_id:
            return self._cached_chat_id

        if configured_id and not configured_id.startswith("@"):
            self._cached_chat_id = configured_id
            return configured_id

        # Query Telegram getUpdates to find who messaged the bot
        try:
            url = f"https://api.telegram.org/bot{token}/getUpdates"
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    for result in reversed(data.get("result", [])):
                        message = result.get("message") or result.get("channel_post") or result.get("my_chat_member")
                        if message and "chat" in message:
                            numeric_id = str(message["chat"]["id"])
                            self._cached_chat_id = numeric_id
                            return numeric_id
        except Exception as e:
            print(f"[Telegram Discovery Notice] {e}")

        # Fallback to configured ID only if not a bot handle
        if configured_id and not configured_id.endswith("_bot"):
            return configured_id
        return None

    async def send_telegram_message(self, text: str) -> bool:
        """Low-level helper to send Markdown-formatted Telegram messages."""
        token = getattr(self.config.profile, "telegram_bot_token", None) or os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id_conf = getattr(self.config.profile, "telegram_chat_id", None) or os.getenv("TELEGRAM_CHAT_ID")

        if not token:
            return False

        chat_id = await self._get_active_chat_id(token, chat_id_conf)
        if not chat_id:
            return False

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": False
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload)
                return resp.status_code == 200
        except Exception as e:
            print(f"Telegram dispatch error: {e}")
            return False

    async def notify_hot_job(self, job: JobModel) -> bool:
        """Sends an alert if a role matches with high score (>=80%) and ultra-fresh recency (<60m)."""
        message = (
            f"🔥 *HUNTERZ HIGH-MATCH JOB DISCOVERED!* 🔥\n\n"
            f"🎯 *Match Score:* `{job.match_score}%`\n"
            f"💼 *Role:* *{job.title}*\n"
            f"🏢 *Company:* *{job.company}*\n"
            f"📍 *Location:* {job.location}\n"
            f"🌐 *Source:* `{job.source.upper()}`\n\n"
            f"🔗 [Open Job Application]({job.url})"
        )
        return await self.send_telegram_message(message)

    async def notify_application_submitted(
        self,
        app: ApplicationModel,
        job: JobModel,
        recruiter_email: Optional[str] = None,
        method: str = "BROWSER_ASHBY_AUTOMATED"
    ) -> bool:
        """Sends an alert whenever HunterZ auto-applies to a job."""
        rec_line = f"👤 *Recruiter Contact:* `{recruiter_email}`\n" if recruiter_email else ""
        notes_line = f"📝 *Status Note:* _{app.response_notes}_\n" if app.response_notes else ""
        dashboard_url = "https://abhiboss07.github.io/HunterZ/"

        message = (
            f"🚀 *HUNTERZ AUTO-APPLIED SUCCESSFULLY!* 🚀\n\n"
            f"🏢 *Company:* *{app.company}*\n"
            f"💼 *Position:* *{app.title}*\n"
            f"🎯 *Match Score:* `{job.match_score}%`\n"
            f"⚙️ *Method:* `{method}`\n"
            f"📄 *Tailored Resume:* `{Path(app.resume_pdf_path).name}`\n"
            f"{rec_line}{notes_line}\n"
            f"📊 [View Live Web CRM Dossier]({dashboard_url})"
        )
        return await self.send_telegram_message(message)

    async def notify_automation_summary(
        self,
        scanned_count: int,
        fresh_count: int,
        applied_count: int,
        applied_companies: List[str]
    ) -> bool:
        """Sends a periodic summary of the autonomous cycle."""
        comps = ", ".join(applied_companies[:5]) if applied_companies else "None (awaiting fresh roles)"
        message = (
            f"⚡ *HUNTERZ AUTOMATION CYCLE COMPLETED* ⚡\n\n"
            f"🔍 *Roles Scanned:* `{scanned_count}`\n"
            f"⏱️ *Ultra-Fresh Roles (<1h):* `{fresh_count}`\n"
            f"📬 *New Auto-Applications:* `{applied_count}`\n"
            f"🏢 *Companies Applied:* {comps}\n\n"
            f"🌐 [Live GitHub Dashboard](https://abhiboss07.github.io/HunterZ/)"
        )
        return await self.send_telegram_message(message)

    async def notify_self_healing_event(self, issue_type: str, action_taken: str) -> bool:
        """Alerts when the self-improvement system identifies and auto-repairs an issue."""
        message = (
            f"🛡️ *HUNTERZ SELF-HEALING SYSTEM TRIGGERED* 🛡️\n\n"
            f"⚠️ *Anomaly Detected:* `{issue_type}`\n"
            f"🔧 *Self-Correction Applied:* {action_taken}\n\n"
            f"_Automated heuristics and resilient rules updated for next cycle._"
        )
        return await self.send_telegram_message(message)
