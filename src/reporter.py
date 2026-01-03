"""HTML report generator using Jinja2 templates."""

import json
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from src.differ import DiffResult


class ReportGenerator:
    """Generate HTML diff reports."""

    def __init__(
        self,
        reports_dir: Path,
        templates_dir: Path,
        base_url: str = "",
    ) -> None:
        self.reports_dir = reports_dir
        self.base_url = base_url.rstrip("/") if base_url else ""
        self._env = Environment(
            loader=FileSystemLoader(templates_dir),
            autoescape=True,
        )

    def _get_date_dir(self, report_time: datetime) -> Path:
        """Get the directory path for a specific date."""
        return (
            self.reports_dir
            / f"{report_time.year:04d}"
            / f"{report_time.month:02d}"
            / f"{report_time.day:02d}"
        )

    def generate_page_diff(self, diff: DiffResult, report_time: datetime) -> Path:
        """Generate HTML page for a single diff."""
        date_dir = self._get_date_dir(report_time)
        date_dir.mkdir(parents=True, exist_ok=True)

        template = self._env.get_template("page_diff.html")
        html = template.render(
            page_slug=diff.page_slug,
            summary=diff.summary,
            html_diff=diff.html_diff,
            unified_diff=diff.unified_diff,
            added_lines=diff.added_lines,
            removed_lines=diff.removed_lines,
            date=report_time.strftime("%Y-%m-%d"),
            timestamp=report_time.strftime("%Y-%m-%d %H:%M:%S UTC"),
        )

        output_path = date_dir / f"{diff.page_slug}.html"
        output_path.write_text(html)
        return output_path

    def generate_daily_index(
        self,
        diffs: list[DiffResult],
        report_time: datetime,
    ) -> Path:
        """Generate daily index page listing all changed pages."""
        date_dir = self._get_date_dir(report_time)
        date_dir.mkdir(parents=True, exist_ok=True)

        changed_pages = [
            {
                "slug": d.page_slug,
                "summary": d.summary,
                "added": d.added_lines,
                "removed": d.removed_lines,
            }
            for d in diffs
            if d.has_changes
        ]

        template = self._env.get_template("daily_index.html")
        html = template.render(
            date=report_time.strftime("%Y-%m-%d"),
            timestamp=report_time.strftime("%Y-%m-%d %H:%M:%S UTC"),
            changed_pages=changed_pages,
            total_changes=len(changed_pages),
        )

        output_path = date_dir / "index.html"
        output_path.write_text(html)

        # Save metadata with timestamp (human-readable format)
        meta_path = date_dir / "meta.json"
        meta_path.write_text(
            json.dumps(
                {
                    "timestamp": report_time.strftime("%b %d, %Y %H:%M UTC"),
                    "count": len(changed_pages),
                }
            )
        )

        return output_path

    def update_main_index(self) -> Path:
        """Update the main index with all report dates."""
        reports: list[dict] = []

        # Scan for all date directories
        for year_dir in sorted(self.reports_dir.iterdir(), reverse=True):
            if not year_dir.is_dir() or not year_dir.name.isdigit():
                continue
            for month_dir in sorted(year_dir.iterdir(), reverse=True):
                if not month_dir.is_dir() or not month_dir.name.isdigit():
                    continue
                for day_dir in sorted(month_dir.iterdir(), reverse=True):
                    if not day_dir.is_dir() or not day_dir.name.isdigit():
                        continue

                    index_file = day_dir / "index.html"
                    if index_file.exists():
                        report_date = f"{year_dir.name}-{month_dir.name}-{day_dir.name}"
                        relative_path = f"{year_dir.name}/{month_dir.name}/{day_dir.name}/"

                        # Try to read metadata for timestamp
                        meta_file = day_dir / "meta.json"
                        if meta_file.exists():
                            meta = json.loads(meta_file.read_text())
                            timestamp = meta.get("timestamp", report_date)
                            page_count = meta.get("count", 0)
                        else:
                            # Fallback for old reports without meta.json
                            timestamp = report_date
                            page_count = sum(
                                1 for f in day_dir.glob("*.html") if f.name != "index.html"
                            )

                        reports.append(
                            {
                                "date": report_date,
                                "timestamp": timestamp,
                                "path": relative_path,
                                "count": page_count,
                            }
                        )

        template = self._env.get_template("main_index.html")
        html = template.render(reports=reports)

        output_path = self.reports_dir / "index.html"
        output_path.write_text(html)
        return output_path

    def get_report_url(self, report_time: datetime) -> str:
        """Get the URL for a specific date's report."""
        date_path = f"{report_time.year:04d}/{report_time.month:02d}/{report_time.day:02d}/"
        if self.base_url:
            return f"{self.base_url}/{date_path}"
        return date_path
