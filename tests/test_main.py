"""Tests for main orchestrator module."""

from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.fetcher import FetchResult
from src.main import DocMonitor


@pytest.fixture
def mock_config(tmp_path: Path) -> MagicMock:
    """Create a mock config."""
    config = MagicMock()
    config.source_base_url = "https://example.com/docs"
    config.source_language = "en"
    config.docs_dir = tmp_path / "docs" / "en"
    config.reports_dir = tmp_path / "reports"
    config.fetcher.concurrency = 2
    config.fetcher.delay = 0.0
    config.fetcher.timeout = 10
    config.fetcher.retry_count = 1
    config.telegram.is_configured = False
    config.github_pages_url = "https://user.github.io/repo"
    config.get_markdown_url = lambda slug: f"https://example.com/docs/en/{slug}.md"
    return config


@pytest.fixture
def templates_dir(tmp_path: Path) -> Path:
    """Create templates directory."""
    templates = tmp_path / "templates"
    templates.mkdir()

    (templates / "page_diff.html").write_text(
        "<html><body><h1>{{ page_slug }}</h1><p>{{ summary }}</p></body></html>"
    )
    (templates / "daily_index.html").write_text("<html><body><h1>{{ date }}</h1></body></html>")
    (templates / "main_index.html").write_text("<html><body><h1>Reports</h1></body></html>")

    return templates


class TestDocMonitor:
    def test_init(self, mock_config: MagicMock, templates_dir: Path) -> None:
        monitor = DocMonitor(mock_config, templates_dir)
        assert monitor.config == mock_config

    async def test_load_stored_content_no_file(
        self,
        mock_config: MagicMock,
        templates_dir: Path,
    ) -> None:
        monitor = DocMonitor(mock_config, templates_dir)

        content = monitor.load_stored_content("nonexistent")

        assert content is None

    async def test_load_stored_content_exists(
        self,
        mock_config: MagicMock,
        templates_dir: Path,
    ) -> None:
        mock_config.docs_dir.mkdir(parents=True)
        (mock_config.docs_dir / "overview.md").write_text("# Overview")

        monitor = DocMonitor(mock_config, templates_dir)
        content = monitor.load_stored_content("overview")

        assert content == "# Overview"

    async def test_save_content(
        self,
        mock_config: MagicMock,
        templates_dir: Path,
    ) -> None:
        monitor = DocMonitor(mock_config, templates_dir)

        monitor.save_content("overview", "# New Content")

        saved = (mock_config.docs_dir / "overview.md").read_text()
        assert saved == "# New Content"

    @patch("src.main.DocumentFetcher")
    async def test_run_no_changes(
        self,
        mock_fetcher_class: MagicMock,
        mock_config: MagicMock,
        templates_dir: Path,
    ) -> None:
        # Set up existing content
        mock_config.docs_dir.mkdir(parents=True)
        (mock_config.docs_dir / "overview.md").write_text("# Overview")

        # Mock fetcher to return same content
        mock_fetcher = AsyncMock()
        mock_fetcher.fetch_all.return_value = [FetchResult("overview", "# Overview", 200)]
        mock_fetcher.__aenter__ = AsyncMock(return_value=mock_fetcher)
        mock_fetcher.__aexit__ = AsyncMock(return_value=None)
        mock_fetcher_class.return_value = mock_fetcher

        monitor = DocMonitor(mock_config, templates_dir)
        result = await monitor.run(["overview"])

        assert result.total_pages == 1
        assert result.changed_pages == 0
        assert result.failed_pages == 0

    @patch("src.main.DocumentFetcher")
    async def test_run_with_changes(
        self,
        mock_fetcher_class: MagicMock,
        mock_config: MagicMock,
        templates_dir: Path,
    ) -> None:
        # Set up existing content
        mock_config.docs_dir.mkdir(parents=True)
        (mock_config.docs_dir / "overview.md").write_text("# Old Overview")

        # Mock fetcher to return new content
        mock_fetcher = AsyncMock()
        mock_fetcher.fetch_all.return_value = [FetchResult("overview", "# New Overview", 200)]
        mock_fetcher.__aenter__ = AsyncMock(return_value=mock_fetcher)
        mock_fetcher.__aexit__ = AsyncMock(return_value=None)
        mock_fetcher_class.return_value = mock_fetcher

        monitor = DocMonitor(mock_config, templates_dir)
        result = await monitor.run(["overview"])

        assert result.total_pages == 1
        assert result.changed_pages == 1
        assert len(result.diffs) == 1
        assert result.diffs[0].has_changes is True

    @patch("src.main.DocumentFetcher")
    async def test_run_with_fetch_error(
        self,
        mock_fetcher_class: MagicMock,
        mock_config: MagicMock,
        templates_dir: Path,
    ) -> None:
        mock_fetcher = AsyncMock()
        mock_fetcher.fetch_all.return_value = [FetchResult("overview", None, 500, "Server error")]
        mock_fetcher.__aenter__ = AsyncMock(return_value=mock_fetcher)
        mock_fetcher.__aexit__ = AsyncMock(return_value=None)
        mock_fetcher_class.return_value = mock_fetcher

        monitor = DocMonitor(mock_config, templates_dir)
        result = await monitor.run(["overview"])

        assert result.failed_pages == 1
        assert result.changed_pages == 0

    @patch("src.main.DocumentFetcher")
    async def test_run_new_page(
        self,
        mock_fetcher_class: MagicMock,
        mock_config: MagicMock,
        templates_dir: Path,
    ) -> None:
        # No existing content
        mock_config.docs_dir.mkdir(parents=True)

        mock_fetcher = AsyncMock()
        mock_fetcher.fetch_all.return_value = [FetchResult("new-page", "# New Page", 200)]
        mock_fetcher.__aenter__ = AsyncMock(return_value=mock_fetcher)
        mock_fetcher.__aexit__ = AsyncMock(return_value=None)
        mock_fetcher_class.return_value = mock_fetcher

        monitor = DocMonitor(mock_config, templates_dir)
        result = await monitor.run(["new-page"])

        assert result.changed_pages == 1
        # New page should be saved
        assert (mock_config.docs_dir / "new-page.md").exists()

    @patch("src.main.DocumentFetcher")
    async def test_run_generates_reports_on_changes(
        self,
        mock_fetcher_class: MagicMock,
        mock_config: MagicMock,
        templates_dir: Path,
    ) -> None:
        mock_config.docs_dir.mkdir(parents=True)
        mock_config.reports_dir.mkdir(parents=True)
        (mock_config.docs_dir / "overview.md").write_text("# Old")

        mock_fetcher = AsyncMock()
        mock_fetcher.fetch_all.return_value = [FetchResult("overview", "# New", 200)]
        mock_fetcher.__aenter__ = AsyncMock(return_value=mock_fetcher)
        mock_fetcher.__aexit__ = AsyncMock(return_value=None)
        mock_fetcher_class.return_value = mock_fetcher

        monitor = DocMonitor(mock_config, templates_dir)
        result = await monitor.run(["overview"], generate_reports=True)

        assert result.changed_pages == 1
        # Check reports were generated
        today = date.today()
        report_dir = (
            mock_config.reports_dir
            / f"{today.year:04d}"
            / f"{today.month:02d}"
            / f"{today.day:02d}"
        )
        assert report_dir.exists()
        assert (report_dir / "overview.html").exists()
        assert (report_dir / "index.html").exists()
