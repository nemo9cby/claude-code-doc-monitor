"""Telegram notification sender."""

from __future__ import annotations

import html
import logging
from datetime import date
from typing import TYPE_CHECKING

from telegram import Bot
from telegram.constants import ParseMode

if TYPE_CHECKING:
    from src.analyzer import AnalysisResult
    from src.main import SourceRunResult

logger = logging.getLogger(__name__)

MAX_MESSAGE_LENGTH = 4096
MAX_PAGES_PER_SOURCE = 5


class TelegramNotifier:
    """Send notifications via Telegram bot."""

    def __init__(self, bot_token: str, chat_id: str) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id

    def format_message(
        self,
        source_results: list[SourceRunResult],
        report_date: date,
        report_url: str,
        analyses: list[AnalysisResult] | None = None,
    ) -> str:
        """Format notification message with HTML for multiple sources."""
        total_changes = sum(r.changed_pages for r in source_results)
        sources_with_changes = [r for r in source_results if r.changed_pages > 0]

        # Create analysis map for lookup
        analysis_map = {a.page_slug: a for a in (analyses or [])}

        lines = [
            f"<b>Documentation Updated ({report_date.isoformat()})</b>",
            "",
            f"{total_changes} {'page' if total_changes == 1 else 'pages'} changed across {len(sources_with_changes)} source(s)",
            "",
        ]

        # Group changes by source
        for source_result in sources_with_changes:
            lines.append(f"<b>📚 {html.escape(source_result.source_name)}</b>")
            lines.append(f"  {source_result.changed_pages} changed")

            # List pages (max per source)
            for diff in source_result.diffs[:MAX_PAGES_PER_SOURCE]:
                slug = html.escape(diff.page_slug)
                summary = html.escape(diff.summary)
                lines.append(f"  • {slug}: {summary}")

                # Add analysis summary if available
                if diff.page_slug in analysis_map:
                    analysis = analysis_map[diff.page_slug]
                    if analysis.analysis:
                        first_line = analysis.analysis.split("\n")[0][:80]
                        analysis_summary = html.escape(first_line)
                        lines.append(f"    <i>{analysis_summary}</i>")

            if source_result.changed_pages > MAX_PAGES_PER_SOURCE:
                remaining = source_result.changed_pages - MAX_PAGES_PER_SOURCE
                lines.append(f"  ... and {remaining} more")

            lines.append("")  # Blank line between sources

        lines.extend(
            [
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
        source_results: list[SourceRunResult],
        report_date: date,
        report_url: str,
        analyses: list[AnalysisResult] | None = None,
    ) -> bool:
        """Send notification about documentation changes."""
        try:
            message = self.format_message(source_results, report_date, report_url, analyses)
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
            message = f"<b>Documentation Monitor Error</b>\n\n{html.escape(error_message)}"
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
