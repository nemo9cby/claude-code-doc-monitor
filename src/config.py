"""Configuration loader for Claude Code doc monitor."""

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class FetcherConfig:
    """Configuration for the HTTP fetcher."""

    concurrency: int = 5
    delay: float = 0.5
    timeout: int = 30
    retry_count: int = 3


@dataclass
class TelegramConfig:
    """Configuration for Telegram notifications."""

    enabled: bool = True
    bot_token: str | None = None
    chat_id: str | None = None

    @property
    def is_configured(self) -> bool:
        return self.enabled and self.bot_token is not None and self.chat_id is not None


@dataclass
class AnalyzerConfig:
    """Configuration for LLM diff analyzer."""

    enabled: bool = True
    model: str = "openai/gpt-4o-mini"
    base_url: str = "https://openrouter.ai/api/v1"
    api_key: str | None = None

    @property
    def is_configured(self) -> bool:
        return self.enabled and self.api_key is not None


@dataclass
class Config:
    """Main configuration container."""

    source_base_url: str
    source_language: str
    docs_dir: Path
    reports_dir: Path
    fetcher: FetcherConfig = field(default_factory=FetcherConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    analyzer: AnalyzerConfig = field(default_factory=AnalyzerConfig)
    github_pages_url: str = ""

    def get_markdown_url(self, page_slug: str) -> str:
        return f"{self.source_base_url}/{self.source_language}/{page_slug}.md"


def load_pages(pages_path: Path) -> list[str]:
    """Load page slugs from pages.yaml."""
    if not pages_path.exists():
        raise FileNotFoundError(f"Pages file not found: {pages_path}")

    with open(pages_path) as f:
        data = yaml.safe_load(f)

    return data.get("pages", [])


def load_config(config_path: Path) -> Config:
    """Load configuration from config.yaml and environment variables."""
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path) as f:
        data = yaml.safe_load(f)

    source = data.get("source", {})
    storage = data.get("storage", {})
    fetcher_data = data.get("fetcher", {})
    telegram_data = data.get("telegram", {})
    analyzer_data = data.get("analyzer", {})
    reports_data = data.get("reports", {})

    fetcher = FetcherConfig(
        concurrency=fetcher_data.get("concurrency", 5),
        delay=fetcher_data.get("delay_between_requests", 0.5),
        timeout=fetcher_data.get("timeout", 30),
        retry_count=fetcher_data.get("retry_count", 3),
    )

    telegram = TelegramConfig(
        enabled=telegram_data.get("enabled", True),
        bot_token=os.environ.get("TELEGRAM_BOT_TOKEN"),
        chat_id=os.environ.get("TELEGRAM_CHAT_ID"),
    )

    analyzer = AnalyzerConfig(
        enabled=analyzer_data.get("enabled", True),
        model=analyzer_data.get("model", "openai/gpt-4o-mini"),
        base_url=analyzer_data.get("base_url", "https://openrouter.ai/api/v1"),
        api_key=os.environ.get("OPENROUTER_API_KEY"),
    )

    return Config(
        source_base_url=source.get("base_url", "https://code.claude.com/docs"),
        source_language=source.get("language", "en"),
        docs_dir=Path(storage.get("docs_dir", "docs/en")),
        reports_dir=Path(storage.get("reports_dir", "reports")),
        fetcher=fetcher,
        telegram=telegram,
        analyzer=analyzer,
        github_pages_url=reports_data.get("github_pages_url", ""),
    )
