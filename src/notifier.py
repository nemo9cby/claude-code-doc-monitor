"""Telegram notification sender."""

import html
import logging
from datetime import date

from telegram import Bot
from telegram.constants import ParseMode

from src.differ import DiffResult

logger = logging.getLogger(__name__)

MAX_MESSAGE_LENGTH = 4096
MAX_PAGES_TO_LIST = 10


class TelegramNotifier:
    """Send notifications via Telegram bot."""

    def __init__(self, bot_token: str, chat_id: str) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id

    def format_message(
        self,
        diffs: list[DiffResult],
        report_date: date,
        report_url: str,
    ) -> str:
        """Format notification message with HTML."""
        changed = [d for d in diffs if d.has_changes]
        count = len(changed)

        lines = [
            f"<b>Claude Code Docs Updated ({report_date.isoformat()})</b>",
            "",
            f"{count} {'page' if count == 1 else 'pages'} changed",
            "",
            "<b>Changed Pages:</b>",
        ]

        # List pages (max 10)
        for diff in changed[:MAX_PAGES_TO_LIST]:
            slug = html.escape(diff.page_slug)
            summary = html.escape(diff.summary)
            lines.append(f"• {slug}: {summary}")

        if count > MAX_PAGES_TO_LIST:
            lines.append(f"... and {count - MAX_PAGES_TO_LIST} more")

        lines.extend(
            [
                "",
                f"<a href='{html.escape(report_url)}'>View Full Diff Report</a>",
            ]
        )

        message = "\n".join(lines)

        # Truncate if needed
        if len(message) > MAX_MESSAGE_LENGTH:
            message = message[: MAX_MESSAGE_LENGTH - 3] + "..."

        return message

    async def send_notification(
        self,
        diffs: list[DiffResult],
        report_date: date,
        report_url: str,
    ) -> bool:
        """Send notification about documentation changes."""
        try:
            message = self.format_message(diffs, report_date, report_url)
            bot = Bot(token=self.bot_token)

            await bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
            return True
        except Exception as e:
            logger.error(f"Failed to send Telegram notification: {e}")
            return False

    async def send_error_notification(self, error_message: str) -> bool:
        """Send error notification."""
        try:
            message = f"<b>Claude Code Doc Monitor Error</b>\n\n{html.escape(error_message)}"
            bot = Bot(token=self.bot_token)

            await bot.send_message(
                chat_id=self.chat_id,
                text=message[:MAX_MESSAGE_LENGTH],
                parse_mode=ParseMode.HTML,
            )
            return True
        except Exception as e:
            logger.error(f"Failed to send error notification: {e}")
            return False
