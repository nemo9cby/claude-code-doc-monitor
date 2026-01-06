"""Tests for main orchestrator module."""

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.config import AnalyzerConfig, Config, FetcherConfig, SourceConfig, TelegramConfig
from src.fetcher import FetchResult
from src.main import DocMonitor


@pytest.fixture
def mock_source(tmp_path: Path) -> SourceConfig:
    """Create a mock source config."""
    return SourceConfig(
        id="test-source",
        name="Test Source",
        base_url="https://example.com/docs",
        language="en",
        docs_dir=tmp_path / "docs" / "test",
        pages_file=Path("config/pages/test.yaml"),
    )


@pytest.fixture
def mock_config(tmp_path: Path) -> Config:
    """Create a mock config."""
    return Config(
        sources=[],  # Will be set per test if needed
        reports_dir=tmp_path / "reports",
        fetcher=FetcherConfig(concurrency=2, delay=0.0, timeout=10, retry_count=1),
        telegram=TelegramConfig(enabled=False),
        analyzer=AnalyzerConfig(enabled=False, api_key=None),
        github_pages_url="https://user.github.io/repo",
    )


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
    def test_init(
        self, mock_source: SourceConfig, mock_config: Config, templates_dir: Path
    ) -> None:
        monitor = DocMonitor(mock_source, mock_config, templates_dir)
        assert monitor.source == mock_source
        assert monitor.config == mock_config

    async def test_load_stored_content_no_file(
        self,
        mock_source: SourceConfig,
        mock_config: Config,
        templates_dir: Path,
    ) -> None:
        monitor = DocMonitor(mock_source, mock_config, templates_dir)

        content = monitor.load_stored_content("nonexistent")

        assert content is None

    async def test_load_stored_content_exists(
        self,
        mock_source: SourceConfig,
        mock_config: Config,
        templates_dir: Path,
    ) -> None:
        mock_source.docs_dir.mkdir(parents=True)
        (mock_source.docs_dir / "overview.md").write_text("# Overview")

        monitor = DocMonitor(mock_source, mock_config, templates_dir)
        content = monitor.load_stored_content("overview")

        assert content == "# Overview"

    async def test_save_content(
        self,
        mock_source: SourceConfig,
        mock_config: Config,
        templates_dir: Path,
    ) -> None:
        monitor = DocMonitor(mock_source, mock_config, templates_dir)

        monitor.save_content("overview", "# New Content")

        saved = (mock_source.docs_dir / "overview.md").read_text()
        assert saved == "# New Content"

    async def test_save_content_nested_path(
        self,
        mock_source: SourceConfig,
        mock_config: Config,
        templates_dir: Path,
    ) -> None:
        monitor = DocMonitor(mock_source, mock_config, templates_dir)

        monitor.save_content("api/messages", "# API Messages")

        saved = (mock_source.docs_dir / "api" / "messages.md").read_text()
        assert saved == "# API Messages"

    @patch("src.main.DocumentFetcher")
    async def test_run_no_changes(
        self,
        mock_fetcher_class: MagicMock,
        mock_source: SourceConfig,
        mock_config: Config,
        templates_dir: Path,
    ) -> None:
        # Set up existing content
        mock_source.docs_dir.mkdir(parents=True)
        (mock_source.docs_dir / "overview.md").write_text("# Overview")

        # Mock fetcher to return same content
        mock_fetcher = AsyncMock()
        mock_fetcher.fetch_all.return_value = [FetchResult("overview", "# Overview", 200)]
        mock_fetcher.__aenter__ = AsyncMock(return_value=mock_fetcher)
        mock_fetcher.__aexit__ = AsyncMock(return_value=None)
        mock_fetcher_class.return_value = mock_fetcher

        monitor = DocMonitor(mock_source, mock_config, templates_dir)
        result = await monitor.run(["overview"])

        assert result.total_pages == 1
        assert result.changed_pages == 0
        assert result.failed_pages == 0

    @patch("src.main.DocumentFetcher")
    async def test_run_with_changes(
        self,
        mock_fetcher_class: MagicMock,
        mock_source: SourceConfig,
        mock_config: Config,
        templates_dir: Path,
    ) -> None:
        # Set up existing content
        mock_source.docs_dir.mkdir(parents=True)
        (mock_source.docs_dir / "overview.md").write_text("# Old Overview")

        # Mock fetcher to return new content
        mock_fetcher = AsyncMock()
        mock_fetcher.fetch_all.return_value = [FetchResult("overview", "# New Overview", 200)]
        mock_fetcher.__aenter__ = AsyncMock(return_value=mock_fetcher)
        mock_fetcher.__aexit__ = AsyncMock(return_value=None)
        mock_fetcher_class.return_value = mock_fetcher

        monitor = DocMonitor(mock_source, mock_config, templates_dir)
        result = await monitor.run(["overview"])

        assert result.total_pages == 1
        assert result.changed_pages == 1
        assert len(result.diffs) == 1
        assert result.diffs[0].has_changes is True

    @patch("src.main.DocumentFetcher")
    async def test_run_with_fetch_error(
        self,
        mock_fetcher_class: MagicMock,
        mock_source: SourceConfig,
        mock_config: Config,
        templates_dir: Path,
    ) -> None:
        mock_fetcher = AsyncMock()
        mock_fetcher.fetch_all.return_value = [FetchResult("overview", None, 500, "Server error")]
        mock_fetcher.__aenter__ = AsyncMock(return_value=mock_fetcher)
        mock_fetcher.__aexit__ = AsyncMock(return_value=None)
        mock_fetcher_class.return_value = mock_fetcher

        monitor = DocMonitor(mock_source, mock_config, templates_dir)
        result = await monitor.run(["overview"])

        assert result.failed_pages == 1
        assert result.changed_pages == 0

    @patch("src.main.DocumentFetcher")
    async def test_run_new_page(
        self,
        mock_fetcher_class: MagicMock,
        mock_source: SourceConfig,
        mock_config: Config,
        templates_dir: Path,
    ) -> None:
        # No existing content
        mock_source.docs_dir.mkdir(parents=True)

        mock_fetcher = AsyncMock()
        mock_fetcher.fetch_all.return_value = [FetchResult("new-page", "# New Page", 200)]
        mock_fetcher.__aenter__ = AsyncMock(return_value=mock_fetcher)
        mock_fetcher.__aexit__ = AsyncMock(return_value=None)
        mock_fetcher_class.return_value = mock_fetcher

        monitor = DocMonitor(mock_source, mock_config, templates_dir)
        result = await monitor.run(["new-page"])

        assert result.changed_pages == 1
        # New page should be saved
        assert (mock_source.docs_dir / "new-page.md").exists()

    @patch("src.main.DocumentFetcher")
    async def test_run_generates_reports_on_changes(
        self,
        mock_fetcher_class: MagicMock,
        mock_source: SourceConfig,
        mock_config: Config,
        templates_dir: Path,
    ) -> None:
        mock_source.docs_dir.mkdir(parents=True)
        mock_config.reports_dir.mkdir(parents=True)
        (mock_source.docs_dir / "overview.md").write_text("# Old")

        mock_fetcher = AsyncMock()
        mock_fetcher.fetch_all.return_value = [FetchResult("overview", "# New", 200)]
        mock_fetcher.__aenter__ = AsyncMock(return_value=mock_fetcher)
        mock_fetcher.__aexit__ = AsyncMock(return_value=None)
        mock_fetcher_class.return_value = mock_fetcher

        monitor = DocMonitor(mock_source, mock_config, templates_dir)
        result = await monitor.run(["overview"], generate_reports=True)

        assert result.changed_pages == 1
        # Check reports were generated (use UTC date since code uses datetime.now(UTC))
        utc_today = datetime.now(UTC).date()
        report_dir = (
            mock_config.reports_dir
            / f"{utc_today.year:04d}"
            / f"{utc_today.month:02d}"
            / f"{utc_today.day:02d}"
        )
        assert report_dir.exists()
        # Reports are now organized by source_id
        assert (report_dir / mock_source.id / "overview.html").exists()
        assert (report_dir / "index.html").exists()
