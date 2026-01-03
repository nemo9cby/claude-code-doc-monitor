"""Tests for config module."""

from pathlib import Path

import pytest

from src.config import Config, FetcherConfig, TelegramConfig, load_config, load_pages


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    """Create a temporary config directory with test files."""
    config_path = tmp_path / "config"
    config_path.mkdir()

    config_yaml = config_path / "config.yaml"
    config_yaml.write_text("""
source:
  base_url: "https://example.com/docs"
  language: "en"

storage:
  docs_dir: "docs/en"
  reports_dir: "reports"

telegram:
  enabled: true

fetcher:
  concurrency: 3
  delay_between_requests: 0.2
  timeout: 15
  retry_count: 2

reports:
  github_pages_url: "https://user.github.io/repo"
""")

    pages_yaml = config_path / "pages.yaml"
    pages_yaml.write_text("""
pages:
  - overview
  - quickstart
  - settings
""")

    return config_path


class TestLoadPages:
    def test_load_pages_from_yaml(self, config_dir: Path) -> None:
        pages = load_pages(config_dir / "pages.yaml")
        assert pages == ["overview", "quickstart", "settings"]

    def test_load_pages_file_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_pages(tmp_path / "nonexistent.yaml")

    def test_load_pages_empty_list(self, tmp_path: Path) -> None:
        pages_yaml = tmp_path / "pages.yaml"
        pages_yaml.write_text("pages: []")
        pages = load_pages(pages_yaml)
        assert pages == []


class TestLoadConfig:
    def test_load_config_from_yaml(self, config_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_token")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")

        config = load_config(config_dir / "config.yaml")

        assert config.source_base_url == "https://example.com/docs"
        assert config.source_language == "en"
        assert config.docs_dir == Path("docs/en")
        assert config.reports_dir == Path("reports")
        assert config.fetcher.concurrency == 3
        assert config.fetcher.delay == 0.2
        assert config.fetcher.timeout == 15
        assert config.fetcher.retry_count == 2
        assert config.telegram.enabled is True
        assert config.telegram.bot_token == "test_token"
        assert config.telegram.chat_id == "12345"
        assert config.github_pages_url == "https://user.github.io/repo"

    def test_load_config_missing_telegram_env(
        self, config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

        config = load_config(config_dir / "config.yaml")

        assert config.telegram.bot_token is None
        assert config.telegram.chat_id is None

    def test_load_config_file_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_config(tmp_path / "nonexistent.yaml")


class TestFetcherConfig:
    def test_default_values(self) -> None:
        config = FetcherConfig()
        assert config.concurrency == 5
        assert config.delay == 0.5
        assert config.timeout == 30
        assert config.retry_count == 3

    def test_custom_values(self) -> None:
        config = FetcherConfig(concurrency=10, delay=1.0, timeout=60, retry_count=5)
        assert config.concurrency == 10
        assert config.delay == 1.0
        assert config.timeout == 60
        assert config.retry_count == 5


class TestTelegramConfig:
    def test_is_configured_true(self) -> None:
        config = TelegramConfig(enabled=True, bot_token="token", chat_id="123")
        assert config.is_configured is True

    def test_is_configured_false_when_disabled(self) -> None:
        config = TelegramConfig(enabled=False, bot_token="token", chat_id="123")
        assert config.is_configured is False

    def test_is_configured_false_when_missing_token(self) -> None:
        config = TelegramConfig(enabled=True, bot_token=None, chat_id="123")
        assert config.is_configured is False

    def test_is_configured_false_when_missing_chat_id(self) -> None:
        config = TelegramConfig(enabled=True, bot_token="token", chat_id=None)
        assert config.is_configured is False


class TestConfig:
    def test_get_markdown_url(self) -> None:
        config = Config(
            source_base_url="https://code.claude.com/docs",
            source_language="en",
            docs_dir=Path("docs/en"),
            reports_dir=Path("reports"),
            fetcher=FetcherConfig(),
            telegram=TelegramConfig(),
            github_pages_url="",
        )
        url = config.get_markdown_url("overview")
        assert url == "https://code.claude.com/docs/en/overview.md"
