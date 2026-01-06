"""Tests for reporter module."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.differ import DiffResult
from src.reporter import ReportGenerator


@pytest.fixture
def reports_dir(tmp_path: Path) -> Path:
    """Create a temporary reports directory."""
    reports = tmp_path / "reports"
    reports.mkdir()
    return reports


@pytest.fixture
def sample_diff() -> DiffResult:
    """Create a sample diff result."""
    return DiffResult(
        page_slug="overview",
        has_changes=True,
        old_content="# Old\n\nOld content",
        new_content="# New\n\nNew content",
        unified_diff="--- a/overview.md\n+++ b/overview.md\n@@ -1,2 +1,2 @@\n-# Old\n+# New",
        html_diff='<span>Old</span><del style="background:#ffe6e6;">Old</del><ins style="background:#e6ffe6;">New</ins>',
        added_lines=2,
        removed_lines=2,
        summary="+2 lines, -2 lines",
    )


@pytest.fixture
def templates_dir(tmp_path: Path) -> Path:
    """Create templates directory with basic templates."""
    templates = tmp_path / "templates"
    templates.mkdir()

    (templates / "page_diff.html").write_text("""
<!DOCTYPE html>
<html>
<head><title>{{ page_slug }} - Diff</title></head>
<body>
<h1>{{ page_slug }}</h1>
<p>{{ summary }}</p>
<div class="diff">{{ html_diff | safe }}</div>
<pre>{{ unified_diff }}</pre>
</body>
</html>
""")

    (templates / "daily_index.html").write_text("""
<!DOCTYPE html>
<html>
<head><title>{{ date }} - Daily Report</title></head>
<body>
<h1>Changes for {{ date }}</h1>
<p>{{ total_changes }} changes in {{ batches|length }} runs</p>
{% for batch in batches %}
<div class="batch">
<h2>{{ batch.timestamp }}</h2>
<ul>
{% for page in batch.pages %}
<li><a href="{{ page.slug }}.html">{{ page.slug }}</a>: {{ page.summary }}</li>
{% endfor %}
</ul>
</div>
{% endfor %}
</body>
</html>
""")

    (templates / "main_index.html").write_text("""
<!DOCTYPE html>
<html>
<head><title>Claude Code Doc Monitor</title></head>
<body>
<h1>All Reports</h1>
<ul>
{% for report in reports %}
<li><a href="{{ report.path }}">{{ report.date }}</a>: {{ report.count }} changes</li>
{% endfor %}
</ul>
</body>
</html>
""")

    return templates


class TestReportGenerator:
    def test_generate_page_diff(
        self,
        reports_dir: Path,
        templates_dir: Path,
        sample_diff: DiffResult,
    ) -> None:
        generator = ReportGenerator(reports_dir, templates_dir)
        report_date = datetime(2026, 1, 3, 14, 30, 0, tzinfo=UTC)

        path = generator.generate_page_diff(sample_diff, report_date)

        assert path.exists()
        assert path.name == "overview.html"
        assert "2026/01/03" in str(path)

        content = path.read_text()
        assert "overview" in content
        assert "+2 lines, -2 lines" in content

    def test_generate_daily_index(
        self,
        reports_dir: Path,
        templates_dir: Path,
        sample_diff: DiffResult,
    ) -> None:
        generator = ReportGenerator(reports_dir, templates_dir)
        report_date = datetime(2026, 1, 3, 14, 30, 0, tzinfo=UTC)

        # First generate a page diff
        generator.generate_page_diff(sample_diff, report_date)

        path = generator.generate_daily_index([sample_diff], report_date)

        assert path.exists()
        assert path.name == "index.html"

        content = path.read_text()
        assert "2026-01-03" in content
        assert "overview" in content

    def test_generate_main_index(
        self,
        reports_dir: Path,
        templates_dir: Path,
        sample_diff: DiffResult,
    ) -> None:
        generator = ReportGenerator(reports_dir, templates_dir)

        # Create a report for a date
        report_date = datetime(2026, 1, 3, 14, 30, 0, tzinfo=UTC)
        generator.generate_page_diff(sample_diff, report_date)
        generator.generate_daily_index([sample_diff], report_date)

        path = generator.update_main_index()

        assert path.exists()
        assert path.name == "index.html"
        assert path.parent == reports_dir

        content = path.read_text()
        assert "2026-01-03" in content

    def test_creates_date_directories(
        self,
        reports_dir: Path,
        templates_dir: Path,
        sample_diff: DiffResult,
    ) -> None:
        generator = ReportGenerator(reports_dir, templates_dir)
        report_date = datetime(2026, 1, 3, 14, 30, 0, tzinfo=UTC)

        generator.generate_page_diff(sample_diff, report_date)

        expected_dir = reports_dir / "2026" / "01" / "03"
        assert expected_dir.exists()
        assert expected_dir.is_dir()

    def test_get_report_url(
        self,
        reports_dir: Path,
        templates_dir: Path,
    ) -> None:
        generator = ReportGenerator(
            reports_dir,
            templates_dir,
            base_url="https://user.github.io/repo",
        )
        report_date = datetime(2026, 1, 3, 14, 30, 0, tzinfo=UTC)

        url = generator.get_report_url(report_date)
        assert url == "https://user.github.io/repo/2026/01/03/"

    def test_get_report_url_no_base(
        self,
        reports_dir: Path,
        templates_dir: Path,
    ) -> None:
        generator = ReportGenerator(reports_dir, templates_dir)
        report_date = datetime(2026, 1, 3, 14, 30, 0, tzinfo=UTC)

        url = generator.get_report_url(report_date)
        assert url == "2026/01/03/"

    def test_multiple_pages_same_day(
        self,
        reports_dir: Path,
        templates_dir: Path,
    ) -> None:
        generator = ReportGenerator(reports_dir, templates_dir)
        report_date = datetime(2026, 1, 3, 14, 30, 0, tzinfo=UTC)

        diff1 = DiffResult(
            page_slug="page1",
            has_changes=True,
            old_content="old",
            new_content="new",
            unified_diff="diff",
            html_diff="html",
            added_lines=1,
            removed_lines=0,
            summary="+1 lines",
        )
        diff2 = DiffResult(
            page_slug="page2",
            has_changes=True,
            old_content="old",
            new_content="new",
            unified_diff="diff",
            html_diff="html",
            added_lines=0,
            removed_lines=1,
            summary="-1 lines",
        )

        generator.generate_page_diff(diff1, report_date)
        generator.generate_page_diff(diff2, report_date)
        index_path = generator.generate_daily_index([diff1, diff2], report_date)

        content = index_path.read_text()
        assert "page1" in content
        assert "page2" in content

    def test_generate_page_diff_nested_path(
        self,
        reports_dir: Path,
        templates_dir: Path,
    ) -> None:
        """Test that nested page slugs create proper directory structure."""
        generator = ReportGenerator(reports_dir, templates_dir)
        report_date = datetime(2026, 1, 6, 14, 30, 0, tzinfo=UTC)

        # Create diff with nested page slug like Anthropic API docs
        diff = DiffResult(
            page_slug="about-claude/models/overview",
            has_changes=True,
            old_content="old",
            new_content="new",
            unified_diff="diff",
            html_diff="html",
            added_lines=1,
            removed_lines=0,
            summary="+1 lines",
        )

        path = generator.generate_page_diff(diff, report_date)

        assert path.exists()
        assert path.name == "overview.html"
        # Should create nested directory structure
        expected_dir = reports_dir / "2026" / "01" / "06" / "about-claude" / "models"
        assert expected_dir.exists()
        assert expected_dir.is_dir()
        assert (expected_dir / "overview.html").exists()
