"""Main orchestrator for documentation monitoring."""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import click
from rich.console import Console
from rich.logging import RichHandler

from src.analyzer import AnalysisResult, DiffAnalyzer
from src.config import Config, load_config, load_pages
from src.differ import DiffResult, DocumentDiffer
from src.fetcher import DocumentFetcher
from src.notifier import TelegramNotifier
from src.reporter import ReportGenerator

logger = logging.getLogger(__name__)
console = Console()


@dataclass
class RunResult:
    """Result of a monitoring run."""

    total_pages: int = 0
    changed_pages: int = 0
    failed_pages: int = 0
    diffs: list[DiffResult] = field(default_factory=list)
    analyses: list[AnalysisResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class DocMonitor:
    """Main orchestrator for documentation monitoring."""

    def __init__(self, config: Config, templates_dir: Path) -> None:
        self.config = config
        self.templates_dir = templates_dir
        self.differ = DocumentDiffer()
        self.analyzer = DiffAnalyzer(
            api_key=config.analyzer.api_key,
            model=config.analyzer.model,
            base_url=config.analyzer.base_url,
        )

    def load_stored_content(self, page_slug: str) -> str | None:
        """Load previously stored content for a page."""
        path = self.config.docs_dir / f"{page_slug}.md"
        if path.exists():
            return path.read_text()
        return None

    def save_content(self, page_slug: str, content: str) -> None:
        """Save page content to storage."""
        self.config.docs_dir.mkdir(parents=True, exist_ok=True)
        path = self.config.docs_dir / f"{page_slug}.md"
        path.write_text(content)

    async def run(
        self,
        pages: list[str],
        generate_reports: bool = False,
        report_time: datetime | None = None,
    ) -> RunResult:
        """Run the monitoring process."""
        result = RunResult(total_pages=len(pages))
        report_time = report_time or datetime.now(UTC)

        async with DocumentFetcher(
            base_url=self.config.source_base_url,
            language=self.config.source_language,
            timeout=self.config.fetcher.timeout,
        ) as fetcher:
            fetch_results = await fetcher.fetch_all(
                pages,
                concurrency=self.config.fetcher.concurrency,
                delay=self.config.fetcher.delay,
            )

        for fetch_result in fetch_results:
            if not fetch_result.is_success:
                result.failed_pages += 1
                result.errors.append(f"{fetch_result.page_slug}: {fetch_result.error}")
                continue

            old_content = self.load_stored_content(fetch_result.page_slug) or ""
            diff = self.differ.compute_diff(
                fetch_result.page_slug,
                old_content,
                fetch_result.content,
            )

            if diff.has_changes:
                result.changed_pages += 1
                result.diffs.append(diff)
                self.save_content(fetch_result.page_slug, fetch_result.content)

        # Analyze diffs with LLM
        if result.diffs and self.analyzer.enabled:
            result.analyses = await self.analyzer.analyze_all(result.diffs)

        if generate_reports and result.diffs:
            self._generate_reports(result.diffs, result.analyses, report_time)

        return result

    def _generate_reports(
        self,
        diffs: list[DiffResult],
        analyses: list[AnalysisResult],
        report_time: datetime,
    ) -> None:
        """Generate HTML reports for changed pages."""
        reporter = ReportGenerator(
            self.config.reports_dir,
            self.templates_dir,
            self.config.github_pages_url,
        )

        # Create a mapping of page_slug -> analysis for easy lookup
        analysis_map = {a.page_slug: a for a in analyses}

        for diff in diffs:
            analysis = analysis_map.get(diff.page_slug)
            reporter.generate_page_diff(diff, report_time, analysis)

        reporter.generate_daily_index(diffs, report_time, analyses)
        reporter.update_main_index()


def setup_logging(verbose: bool = False) -> None:
    """Configure logging with rich output."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )


@click.command()
@click.option("--config", "config_path", default="config/config.yaml", help="Config file path")
@click.option("--pages", "pages_path", default="config/pages.yaml", help="Pages file path")
@click.option("--templates", "templates_path", default="templates", help="Templates directory")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
@click.option("--no-notify", is_flag=True, help="Skip Telegram notification")
@click.option("--no-reports", is_flag=True, help="Skip report generation")
def cli(
    config_path: str,
    pages_path: str,
    templates_path: str,
    verbose: bool,
    no_notify: bool,
    no_reports: bool,
) -> None:
    """Monitor Claude Code documentation for updates."""
    setup_logging(verbose)

    try:
        config = load_config(Path(config_path))
        pages = load_pages(Path(pages_path))
        templates_dir = Path(templates_path)

        console.print("[bold]Claude Code Doc Monitor[/bold]")
        console.print(f"Monitoring {len(pages)} pages...")

        monitor = DocMonitor(config, templates_dir)
        result = asyncio.run(monitor.run(pages, generate_reports=not no_reports))

        console.print("\n[bold]Results:[/bold]")
        console.print(f"  Total pages: {result.total_pages}")
        console.print(f"  Changed: {result.changed_pages}")
        console.print(f"  Failed: {result.failed_pages}")

        if result.diffs:
            console.print("\n[bold]Changed pages:[/bold]")
            analysis_map = {a.page_slug: a for a in result.analyses}
            for diff in result.diffs:
                console.print(f"  • {diff.page_slug}: {diff.summary}")
                if diff.page_slug in analysis_map:
                    analysis = analysis_map[diff.page_slug]
                    # Show first line of analysis
                    first_line = analysis.analysis.split("\n")[0][:100] if analysis.analysis else ""
                    console.print(f"    [dim]{first_line}[/dim]")

        if result.errors:
            console.print("\n[bold red]Errors:[/bold red]")
            for error in result.errors:
                console.print(f"  • {error}")

        # Send notification
        if config.telegram.is_configured and not no_notify and result.diffs:
            console.print("\nSending Telegram notification...")
            now = datetime.now(UTC)
            notifier = TelegramNotifier(
                config.telegram.bot_token,
                config.telegram.chat_id,
            )
            report_url = ReportGenerator(
                config.reports_dir,
                templates_dir,
                config.github_pages_url,
            ).get_report_url(now)

            success = asyncio.run(
                notifier.send_notification(result.diffs, now.date(), report_url, result.analyses)
            )
            if success:
                console.print("[green]Notification sent![/green]")
            else:
                console.print("[red]Failed to send notification[/red]")

    except FileNotFoundError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise SystemExit(1) from None
    except Exception as e:
        logger.exception("Unexpected error")
        console.print(f"[red]Error: {e}[/red]")
        raise SystemExit(1) from None


if __name__ == "__main__":
    cli()
