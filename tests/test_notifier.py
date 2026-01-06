"""Tests for notifier module."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.differ import DiffResult
from src.main import SourceRunResult
from src.notifier import TelegramNotifier


def make_diff(
    page_slug: str, added: int = 1, removed: int = 0, summary: str | None = None
) -> DiffResult:
    """Helper to create a DiffResult."""
    return DiffResult(
        page_slug=page_slug,
        has_changes=True,
        old_content="old",
        new_content="new",
        unified_diff="diff",
        html_diff="html",
        added_lines=added,
        removed_lines=removed,
        summary=summary or f"+{added} lines, -{removed} lines",
    )


def make_source_result(
    source_id: str = "test",
    source_name: str = "Test Source",
    diffs: list[DiffResult] | None = None,
) -> SourceRunResult:
    """Helper to create a SourceRunResult."""
    diffs = diffs or []
    return SourceRunResult(
        source_id=source_id,
        source_name=source_name,
        total_pages=len(diffs),
        changed_pages=len(diffs),
        failed_pages=0,
        diffs=diffs,
        analyses=[],
        errors=[],
    )


@pytest.fixture
def sample_source_results() -> list[SourceRunResult]:
    """Create sample source results for testing."""
    diffs = [
        make_diff("overview", added=5, removed=2, summary="+5 lines, -2 lines"),
        make_diff("quickstart", added=3, removed=0, summary="+3 lines"),
    ]
    return [make_source_result("claude-code", "Claude Code", diffs)]


class TestTelegramNotifier:
    @pytest.fixture
    def notifier(self) -> TelegramNotifier:
        return TelegramNotifier(bot_token="test_token", chat_id="12345")

    def test_format_message(
        self, notifier: TelegramNotifier, sample_source_results: list[SourceRunResult]
    ) -> None:
        report_date = date(2026, 1, 3)
        report_url = "https://user.github.io/repo/2026/01/03/"

        message = notifier.format_message(sample_source_results, report_date, report_url)

        assert "Documentation Updated" in message
        assert "2026-01-03" in message
        assert "2 pages changed" in message
        assert "Claude Code" in message
        assert "overview" in message
        assert "quickstart" in message
        assert report_url in message

    def test_format_message_single_page(self, notifier: TelegramNotifier) -> None:
        diffs = [make_diff("hooks", added=1)]
        source_results = [make_source_result("test", "Test", diffs)]
        report_date = date(2026, 1, 3)

        message = notifier.format_message(source_results, report_date, "https://example.com")

        assert "1 page changed" in message
        assert "hooks" in message

    def test_format_message_multiple_sources(self, notifier: TelegramNotifier) -> None:
        source1 = make_source_result("claude-code", "Claude Code", [make_diff("overview")])
        source2 = make_source_result(
            "api", "Anthropic API", [make_diff("messages"), make_diff("tools")]
        )
        source_results = [source1, source2]
        report_date = date(2026, 1, 3)

        message = notifier.format_message(source_results, report_date, "https://example.com")

        assert "3 pages changed across 2 source(s)" in message
        assert "Claude Code" in message
        assert "Anthropic API" in message
        assert "overview" in message
        assert "messages" in message
        assert "tools" in message

    def test_format_message_truncates_long_list(self, notifier: TelegramNotifier) -> None:
        # Create 15 diffs in one source
        diffs = [make_diff(f"page{i}") for i in range(15)]
        source_results = [make_source_result("test", "Test", diffs)]
        report_date = date(2026, 1, 3)

        message = notifier.format_message(source_results, report_date, "https://example.com")

        assert "15 pages changed" in message
        assert "and 10 more" in message  # MAX_PAGES_PER_SOURCE is 5
        # Should only list first 5 per source
        assert "page0" in message
        assert "page4" in message
        assert "page14" not in message  # Should be truncated

    def test_format_message_html_escaping(self, notifier: TelegramNotifier) -> None:
        diffs = [make_diff("test<script>", summary="<script>alert('xss')</script>")]
        source_results = [make_source_result("test", "Test<b>", diffs)]
        report_date = date(2026, 1, 3)

        message = notifier.format_message(source_results, report_date, "https://example.com")

        # Should escape HTML entities
        assert "<script>" not in message
        assert "&lt;script&gt;" in message

    @patch("src.notifier.Bot")
    async def test_send_notification_success(
        self,
        mock_bot_class: MagicMock,
        notifier: TelegramNotifier,
        sample_source_results: list[SourceRunResult],
    ) -> None:
        mock_bot = AsyncMock()
        mock_bot_class.return_value = mock_bot

        report_date = date(2026, 1, 3)
        report_url = "https://user.github.io/repo/2026/01/03/"

        result = await notifier.send_notification(sample_source_results, report_date, report_url)

        assert result is True
        mock_bot.send_message.assert_called_once()
        call_args = mock_bot.send_message.call_args
        assert call_args.kwargs["chat_id"] == "12345"
        assert "Documentation Updated" in call_args.kwargs["text"]

    @patch("src.notifier.Bot")
    async def test_send_notification_failure(
        self,
        mock_bot_class: MagicMock,
        notifier: TelegramNotifier,
        sample_source_results: list[SourceRunResult],
    ) -> None:
        mock_bot = AsyncMock()
        mock_bot.send_message.side_effect = Exception("Network error")
        mock_bot_class.return_value = mock_bot

        report_date = date(2026, 1, 3)

        result = await notifier.send_notification(
            sample_source_results, report_date, "https://example.com"
        )

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
        # Create diffs with very long summaries
        diffs = [make_diff(f"page{i}", summary="x" * 500) for i in range(10)]
        source_results = [make_source_result("test", "Test", diffs)]
        report_date = date(2026, 1, 3)

        message = notifier.format_message(source_results, report_date, "https://example.com")

        # Telegram message limit is 4096 characters
        assert len(message) <= 4096
