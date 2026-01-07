"""Main orchestrator for documentation monitoring."""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import click
from dotenv import load_dotenv
from rich.console import Console
from rich.logging import RichHandler

from src.analyzer import AnalysisResult, DiffAnalyzer
from src.config import Config, SourceConfig, load_config, load_pages
from src.differ import DiffResult, DocumentDiffer
from src.fetcher import DocumentFetcher
from src.notifier import TelegramNotifier
from src.reporter import ReportGenerator

# Use US Eastern Time for display and notifications
EST = ZoneInfo("America/New_York")

logger = logging.getLogger(__name__)
console = Console()


@dataclass
class SourceRunResult:
    """Result of monitoring a single source."""

    source_id: str
    source_name: str
    total_pages: int = 0
    changed_pages: int = 0
    failed_pages: int = 0
    diffs: list[DiffResult] = field(default_factory=list)
    analyses: list[AnalysisResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class RunResult:
    """Result of a complete monitoring run across all sources."""

    source_results: list[SourceRunResult] = field(default_factory=list)

    @property
    def total_pages(self) -> int:
        return sum(r.total_pages for r in self.source_results)

    @property
    def changed_pages(self) -> int:
        return sum(r.changed_pages for r in self.source_results)

    @property
    def failed_pages(self) -> int:
        return sum(r.failed_pages for r in self.source_results)

    @property
    def all_diffs(self) -> list[DiffResult]:
        diffs = []
        for r in self.source_results:
            diffs.extend(r.diffs)
        return diffs

    @property
    def all_analyses(self) -> list[AnalysisResult]:
        analyses = []
        for r in self.source_results:
            analyses.extend(r.analyses)
        return analyses

    @property
    def has_changes(self) -> bool:
        return self.changed_pages > 0


class DocMonitor:
    """Monitor for a single documentation source."""

    def __init__(
        self,
        source: SourceConfig,
        config: Config,
        templates_dir: Path,
    ) -> None:
        self.source = source
        self.config = config
        self.templates_dir = templates_dir
        self.differ = DocumentDiffer()
        self.analyzer = DiffAnalyzer(
            api_key=config.analyzer.api_key,
            model=config.analyzer.model,
            base_url=config.analyzer.base_url,
            temperature=config.analyzer.temperature,
            max_tokens=config.analyzer.max_tokens,
            timeout_seconds=config.analyzer.timeout_seconds,
        )

    def load_stored_content(self, page_slug: str) -> str | None:
        """Load previously stored content for a page."""
        path = self.source.docs_dir / f"{page_slug}.md"
        if path.exists():
            return path.read_text()
        return None

    def save_content(self, page_slug: str, content: str) -> None:
        """Save page content to storage."""
        self.source.docs_dir.mkdir(parents=True, exist_ok=True)
        path = self.source.docs_dir / f"{page_slug}.md"
        # Create parent directories for nested paths (e.g., api/messages)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    async def run(
        self,
        pages: list[str],
        generate_reports: bool = False,
        report_time: datetime | None = None,
    ) -> SourceRunResult:
        """Run the monitoring process for this source."""
        result = SourceRunResult(
            source_id=self.source.id,
            source_name=self.source.name,
            total_pages=len(pages),
        )
        report_time = report_time or datetime.now(UTC)

        async with DocumentFetcher(
            base_url=self.source.base_url,
            language=self.source.language,
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
                # Tag diff with source info
                diff.source_id = self.source.id
                diff.source_name = self.source.name
                result.diffs.append(diff)
                self.save_content(fetch_result.page_slug, fetch_result.content)

        # Per-file analysis is disabled in favor of batch analysis (done at top level).
        # We keep the capability here if needed in the future, but do not invoke it by default.

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

        # Note: Daily index generation is deferred to the CLI to support batch analysis
        # across all sources. Only generate page diffs here.


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
@click.option("--templates", "templates_path", default="templates", help="Templates directory")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
@click.option("--no-notify", is_flag=True, help="Skip Telegram notification")
@click.option("--no-reports", is_flag=True, help="Skip report generation")
@click.option("--source", "source_filter", default=None, help="Only monitor specific source ID")
def cli(
    config_path: str,
    templates_path: str,
    verbose: bool,
    no_notify: bool,
    no_reports: bool,
    source_filter: str | None,
) -> None:
    """Monitor documentation sources for updates."""
    # Load .env file for local development
    load_dotenv()
    setup_logging(verbose)

    try:
        config = load_config(Path(config_path))
        templates_dir = Path(templates_path)

        # Filter sources if requested
        sources = config.sources
        if source_filter:
            sources = [s for s in sources if s.id == source_filter]
            if not sources:
                console.print(f"[red]Error: Source '{source_filter}' not found[/red]")
                raise SystemExit(1)

        console.print("[bold]Documentation Monitor[/bold]")
        console.print(f"Monitoring {len(sources)} source(s)...")

        result = RunResult()
        # Use a single timestamp for the entire run to group into one batch on the index
        run_report_time = datetime.now(UTC)

        for source in sources:
            console.print(f"\n[bold cyan]Source: {source.name}[/bold cyan]")

            # Load pages for this source
            pages = load_pages(source.pages_file)
            console.print(f"  Checking {len(pages)} pages...")

            monitor = DocMonitor(source, config, templates_dir)
            # Generate per-page diffs now, but defer daily index + batch analysis to end
            source_result = asyncio.run(
                monitor.run(pages, generate_reports=not no_reports, report_time=run_report_time)
            )
            result.source_results.append(source_result)

            console.print(f"  Changed: {source_result.changed_pages}")
            console.print(f"  Failed: {source_result.failed_pages}")

            if source_result.diffs:
                analysis_map = {a.page_slug: a for a in source_result.analyses}
                for diff in source_result.diffs:
                    console.print(f"    • {diff.page_slug}: {diff.summary}")
                    if diff.page_slug in analysis_map:
                        analysis = analysis_map[diff.page_slug]
                        first_line = (
                            analysis.analysis.split("\n")[0][:80] if analysis.analysis else ""
                        )
                        console.print(f"      [dim]{first_line}[/dim]")

            if source_result.errors:
                for error in source_result.errors[:5]:  # Show first 5 errors
                    console.print(f"    [red]✗ {error}[/red]")
                if len(source_result.errors) > 5:
                    console.print(f"    [red]... and {len(source_result.errors) - 5} more[/red]")

        # Summary
        console.print("\n[bold]Summary:[/bold]")
        console.print(f"  Total pages: {result.total_pages}")
        console.print(f"  Changed: {result.changed_pages}")
        console.print(f"  Failed: {result.failed_pages}")

        # Generate the daily index once with batch AI analysis across all sources
        if not no_reports and result.has_changes:
            reporter = ReportGenerator(
                config.reports_dir,
                templates_dir,
                config.github_pages_url,
            )

            # Perform batch-level AI analysis across all diffs
            batch_analysis_text = None
            batch_reasoning_text = None
            if config.analyzer.enabled and config.analyzer.api_key and config.analyzer.model:
                analyzer = DiffAnalyzer(
                    api_key=config.analyzer.api_key,
                    model=config.analyzer.model,
                    base_url=config.analyzer.base_url,
                    temperature=config.analyzer.temperature,
                    max_tokens=config.analyzer.max_tokens,
                    timeout_seconds=config.analyzer.timeout_seconds,
                )
                batch_result = asyncio.run(analyzer.analyze_batch(result.all_diffs))
                if batch_result:
                    batch_analysis_text = batch_result.analysis
                    batch_reasoning_text = batch_result.reasoning or None

            reporter.generate_daily_index(
                result.all_diffs,
                run_report_time,
                analyses=None,
                batch_analysis=batch_analysis_text,
                batch_reasoning=batch_reasoning_text,
            )
            reporter.update_main_index()

        # Send notification
        if config.telegram.is_configured and not no_notify and result.has_changes:
            console.print("\nSending Telegram notification...")
            now = run_report_time
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
                notifier.send_notification(
                    result.source_results,
                    now.astimezone(EST).date(),
                    report_url,
                    result.all_analyses,
                )
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
