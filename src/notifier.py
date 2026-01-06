"""Telegram notification sender."""

from __future__ import annotations

import html
import logging
from datetime import date
from typing import TYPE_CHECKING

from telegram import Bot
from telegram.constants import ParseMode

from src.differ import DiffResult

if TYPE_CHECKING:
    from src.analyzer import AnalysisResult

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
        analyses: list[AnalysisResult] | None = None,
    ) -> str:
        """Format notification message with HTML."""
        changed = [d for d in diffs if d.has_changes]
        count = len(changed)

        # Create analysis map for lookup
        analysis_map = {a.page_slug: a for a in (analyses or [])}

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

            # Add analysis summary if available
            if slug in analysis_map:
                analysis = analysis_map[slug]
                # Use first line of markdown analysis as summary
                first_line = analysis.analysis.split("\n")[0][:100] if analysis.analysis else ""
                analysis_summary = html.escape(first_line)
                lines.append(f"  <i>{analysis_summary}</i>")

        if count > MAX_PAGES_TO_LIST:
            lines.append(f"... and {count - MAX_PAGES_TO_LIST} more")

        lines.extend(
            [
                "",
                f'<a href="{report_url}">View Full Diff Report</a>',
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
        analyses: list[AnalysisResult] | None = None,
    ) -> bool:
        """Send notification about documentation changes."""
        try:
            message = self.format_message(diffs, report_date, report_url, analyses)
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
