"""Tests for notifier module."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.differ import DiffResult
from src.notifier import TelegramNotifier


@pytest.fixture
def sample_diffs() -> list[DiffResult]:
    """Create sample diff results for testing."""
    return [
        DiffResult(
            page_slug="overview",
            has_changes=True,
            old_content="old",
            new_content="new",
            unified_diff="diff",
            html_diff="html",
            added_lines=5,
            removed_lines=2,
            summary="+5 lines, -2 lines",
        ),
        DiffResult(
            page_slug="quickstart",
            has_changes=True,
            old_content="old",
            new_content="new",
            unified_diff="diff",
            html_diff="html",
            added_lines=3,
            removed_lines=0,
            summary="+3 lines",
        ),
    ]


class TestTelegramNotifier:
    @pytest.fixture
    def notifier(self) -> TelegramNotifier:
        return TelegramNotifier(bot_token="test_token", chat_id="12345")

    def test_format_message(
        self, notifier: TelegramNotifier, sample_diffs: list[DiffResult]
    ) -> None:
        report_date = date(2026, 1, 3)
        report_url = "https://user.github.io/repo/2026/01/03/"

        message = notifier.format_message(sample_diffs, report_date, report_url)

        assert "Claude Code Docs Updated" in message
        assert "2026-01-03" in message
        assert "2 pages changed" in message
        assert "overview" in message
        assert "quickstart" in message
        assert report_url in message

    def test_format_message_single_page(self, notifier: TelegramNotifier) -> None:
        diffs = [
            DiffResult(
                page_slug="hooks",
                has_changes=True,
                old_content="old",
                new_content="new",
                unified_diff="",
                html_diff="",
                added_lines=1,
                removed_lines=0,
                summary="+1 lines",
            )
        ]
        report_date = date(2026, 1, 3)

        message = notifier.format_message(diffs, report_date, "https://example.com")

        assert "1 page changed" in message
        assert "hooks" in message

    def test_format_message_truncates_long_list(self, notifier: TelegramNotifier) -> None:
        # Create 15 diffs
        diffs = [
            DiffResult(
                page_slug=f"page{i}",
                has_changes=True,
                old_content="old",
                new_content="new",
                unified_diff="",
                html_diff="",
                added_lines=1,
                removed_lines=0,
                summary="+1 lines",
            )
            for i in range(15)
        ]
        report_date = date(2026, 1, 3)

        message = notifier.format_message(diffs, report_date, "https://example.com")

        assert "15 pages changed" in message
        assert "and 5 more" in message
        # Should only list first 10
        assert "page0" in message
        assert "page9" in message
        assert "page14" not in message  # Should be truncated

    def test_format_message_html_escaping(self, notifier: TelegramNotifier) -> None:
        diffs = [
            DiffResult(
                page_slug="test<script>",
                has_changes=True,
                old_content="old",
                new_content="new",
                unified_diff="",
                html_diff="",
                added_lines=1,
                removed_lines=0,
                summary="<script>alert('xss')</script>",
            )
        ]
        report_date = date(2026, 1, 3)

        message = notifier.format_message(diffs, report_date, "https://example.com")

        # Should escape HTML entities
        assert "<script>" not in message
        assert "&lt;script&gt;" in message

    @patch("src.notifier.Bot")
    async def test_send_notification_success(
        self,
        mock_bot_class: MagicMock,
        notifier: TelegramNotifier,
        sample_diffs: list[DiffResult],
    ) -> None:
        mock_bot = AsyncMock()
        mock_bot_class.return_value = mock_bot

        report_date = date(2026, 1, 3)
        report_url = "https://user.github.io/repo/2026/01/03/"

        result = await notifier.send_notification(sample_diffs, report_date, report_url)

        assert result is True
        mock_bot.send_message.assert_called_once()
        call_args = mock_bot.send_message.call_args
        assert call_args.kwargs["chat_id"] == "12345"
        assert "Claude Code Docs Updated" in call_args.kwargs["text"]

    @patch("src.notifier.Bot")
    async def test_send_notification_failure(
        self,
        mock_bot_class: MagicMock,
        notifier: TelegramNotifier,
        sample_diffs: list[DiffResult],
    ) -> None:
        mock_bot = AsyncMock()
        mock_bot.send_message.side_effect = Exception("Network error")
        mock_bot_class.return_value = mock_bot

        report_date = date(2026, 1, 3)

        result = await notifier.send_notification(sample_diffs, report_date, "https://example.com")

        assert result is False

    @patch("src.notifier.Bot")
    async def test_send_error_notification(
        self,
        mock_bot_class: MagicMock,
        notifier: TelegramNotifier,
    ) -> None:
        mock_bot = AsyncMock()
        mock_bot_class.return_value = mock_bot

        result = await notifier.send_error_notification("Fetch failed: timeout")

        assert result is True
        mock_bot.send_message.assert_called_once()
        call_args = mock_bot.send_message.call_args
        assert "Error" in call_args.kwargs["text"]
        assert "timeout" in call_args.kwargs["text"]

    def test_message_length_limit(self, notifier: TelegramNotifier) -> None:
        # Create a very long diff summary
        diffs = [
            DiffResult(
                page_slug=f"page{i}",
                has_changes=True,
                old_content="old",
                new_content="new",
                unified_diff="",
                html_diff="",
                added_lines=1,
                removed_lines=0,
                summary="x" * 500,  # Very long summary
            )
            for i in range(10)
        ]
        report_date = date(2026, 1, 3)

        message = notifier.format_message(diffs, report_date, "https://example.com")

        # Telegram message limit is 4096 characters
        assert len(message) <= 4096
