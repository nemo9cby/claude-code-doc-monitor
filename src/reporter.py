"""HTML report generator using Jinja2 templates."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader

# Use US Eastern Time for display
EST = ZoneInfo("America/New_York")

from src.differ import DiffResult

if TYPE_CHECKING:
    from src.analyzer import AnalysisResult


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
        """Get the directory path for a specific date (in EST)."""
        # Convert to EST for consistent date folder naming
        est_time = report_time.astimezone(EST)
        return (
            self.reports_dir
            / f"{est_time.year:04d}"
            / f"{est_time.month:02d}"
            / f"{est_time.day:02d}"
        )

    def generate_page_diff(
        self,
        diff: DiffResult,
        report_time: datetime,
        analysis: AnalysisResult | None = None,
    ) -> Path:
        """Generate HTML page for a single diff."""
        date_dir = self._get_date_dir(report_time)
        date_dir.mkdir(parents=True, exist_ok=True)

        # Calculate relative path back to daily index based on nesting depth
        # source_id/page_slug.html -> ../index.html
        # source_id/nested/page.html -> ../../index.html
        source_id = diff.source_id or "unknown"
        depth = diff.page_slug.count("/") + 1  # +1 for source_id prefix
        back_to_index = "../" * depth + "index.html"

        template = self._env.get_template("page_diff.html")
        html = template.render(
            page_slug=diff.page_slug,
            source_id=source_id,
            source_name=diff.source_name or source_id,
            summary=diff.summary,
            html_diff=diff.html_diff,
            unified_diff=diff.unified_diff,
            added_lines=diff.added_lines,
            removed_lines=diff.removed_lines,
            date=report_time.strftime("%Y-%m-%d"),
            timestamp=report_time.astimezone(EST).strftime("%Y-%m-%d %H:%M:%S EST"),
            analysis=analysis,
            back_to_index=back_to_index,
        )

        # Organize by source: date_dir/source_id/page_slug.html
        output_path = date_dir / source_id / f"{diff.page_slug}.html"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html)
        return output_path

    def generate_daily_index(
        self,
        diffs: list[DiffResult],
        report_time: datetime,
        analyses: list[AnalysisResult] | None = None,
        batch_analysis: str | None = None,
    ) -> Path:
        """Generate daily index page listing all changed pages, accumulating multiple runs."""
        date_dir = self._get_date_dir(report_time)
        date_dir.mkdir(parents=True, exist_ok=True)

        # Load existing batches from meta.json if it exists
        meta_path = date_dir / "meta.json"
        if meta_path.exists():
            meta = json.loads(meta_path.read_text())
            batches = meta.get("batches", [])
        else:
            batches = []

        # Create analysis map for lookup
        analysis_map = {a.page_slug: a for a in (analyses or [])}

        def serialize_analysis(analysis: AnalysisResult | None) -> dict | None:
            if analysis is None:
                return None
            return {"analysis": analysis.analysis}

        # Create new batch for this run, grouped by source
        pages_by_source: dict[str, list[dict]] = {}
        for d in diffs:
            if not d.has_changes:
                continue
            source_id = d.source_id or "unknown"
            source_name = d.source_name or source_id
            if source_id not in pages_by_source:
                pages_by_source[source_id] = []
            pages_by_source[source_id].append(
                {
                    "slug": d.page_slug,
                    "source_id": source_id,
                    "source_name": source_name,
                    "summary": d.summary,
                    "added": d.added_lines,
                    "removed": d.removed_lines,
                    "analysis": serialize_analysis(analysis_map.get(d.page_slug)),
                }
            )

        # Build sources list with their pages
        sources = [
            {"id": src_id, "name": pages[0]["source_name"], "pages": pages}
            for src_id, pages in pages_by_source.items()
        ]

        new_batch = {
            "timestamp": report_time.astimezone(EST).strftime("%H:%M EST"),
            "sources": sources,
            # Keep flat pages list for backward compatibility and totals
            "pages": [p for pages in pages_by_source.values() for p in pages],
        }
        if batch_analysis:
            new_batch["analysis"] = batch_analysis
        batches.append(new_batch)

        # Calculate totals
        total_changes = sum(len(b.get("pages", [])) for b in batches)

        template = self._env.get_template("daily_index.html")
        html = template.render(
            date=report_time.strftime("%Y-%m-%d"),
            batches=list(reversed(batches)),  # Most recent first
            total_changes=total_changes,
        )

        output_path = date_dir / "index.html"
        output_path.write_text(html)

        # Save metadata with all batches
        meta_path.write_text(
            json.dumps(
                {
                    "timestamp": report_time.astimezone(EST).strftime("%b %d, %Y %H:%M EST"),
                    "count": total_changes,
                    "batches": batches,
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
