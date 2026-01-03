"""Tests for differ module."""

import pytest

from src.differ import DiffResult, DocumentDiffer


class TestDiffResult:
    def test_no_changes(self) -> None:
        result = DiffResult(
            page_slug="overview",
            has_changes=False,
            old_content="# Hello",
            new_content="# Hello",
            unified_diff="",
            html_diff="",
            added_lines=0,
            removed_lines=0,
            summary="No changes",
        )
        assert result.has_changes is False
        assert result.summary == "No changes"

    def test_with_changes(self) -> None:
        result = DiffResult(
            page_slug="overview",
            has_changes=True,
            old_content="# Hello",
            new_content="# Hello World",
            unified_diff="diff...",
            html_diff="<span>diff</span>",
            added_lines=1,
            removed_lines=1,
            summary="+1 lines, -1 lines",
        )
        assert result.has_changes is True
        assert result.added_lines == 1
        assert result.removed_lines == 1


class TestDocumentDiffer:
    @pytest.fixture
    def differ(self) -> DocumentDiffer:
        return DocumentDiffer()

    def test_no_changes(self, differ: DocumentDiffer) -> None:
        content = "# Overview\n\nSome text here."
        result = differ.compute_diff("overview", content, content)

        assert result.has_changes is False
        assert result.page_slug == "overview"
        assert result.unified_diff == ""
        assert result.html_diff == ""
        assert result.added_lines == 0
        assert result.removed_lines == 0
        assert result.summary == "No changes"

    def test_simple_addition(self, differ: DocumentDiffer) -> None:
        old = "# Overview\n\nLine 1"
        new = "# Overview\n\nLine 1\nLine 2"

        result = differ.compute_diff("overview", old, new)

        assert result.has_changes is True
        assert result.added_lines >= 1
        assert "+Line 2" in result.unified_diff
        assert "a/overview.md" in result.unified_diff
        assert "b/overview.md" in result.unified_diff

    def test_simple_removal(self, differ: DocumentDiffer) -> None:
        old = "# Overview\n\nLine 1\nLine 2"
        new = "# Overview\n\nLine 1"

        result = differ.compute_diff("overview", old, new)

        assert result.has_changes is True
        assert result.removed_lines >= 1
        assert "-Line 2" in result.unified_diff

    def test_modification(self, differ: DocumentDiffer) -> None:
        old = "# Overview\n\nOld text"
        new = "# Overview\n\nNew text"

        result = differ.compute_diff("overview", old, new)

        assert result.has_changes is True
        assert "-Old text" in result.unified_diff
        assert "+New text" in result.unified_diff

    def test_html_diff_generated(self, differ: DocumentDiffer) -> None:
        old = "Hello world"
        new = "Hello there world"

        result = differ.compute_diff("test", old, new)

        assert result.has_changes is True
        assert result.html_diff != ""
        # diff-match-patch uses ins/del or span with style
        assert "<" in result.html_diff

    def test_summary_format(self, differ: DocumentDiffer) -> None:
        old = "Line 1\nLine 2\nLine 3"
        new = "Line 1\nLine 2 modified\nLine 4\nLine 5"

        result = differ.compute_diff("test", old, new)

        assert result.has_changes is True
        # Summary should mention added/removed lines
        assert "+" in result.summary or "-" in result.summary

    def test_empty_old_content(self, differ: DocumentDiffer) -> None:
        result = differ.compute_diff("new-page", "", "# New Page\n\nContent")

        assert result.has_changes is True
        assert result.added_lines > 0

    def test_empty_new_content(self, differ: DocumentDiffer) -> None:
        result = differ.compute_diff("deleted-page", "# Old Page\n\nContent", "")

        assert result.has_changes is True
        assert result.removed_lines > 0

    def test_whitespace_only_changes(self, differ: DocumentDiffer) -> None:
        old = "# Title\n\nContent"
        new = "# Title\n\nContent\n"

        result = differ.compute_diff("page", old, new)

        # Trailing newline is still a change
        assert result.has_changes is True

    def test_preserves_content(self, differ: DocumentDiffer) -> None:
        old = "old content"
        new = "new content"

        result = differ.compute_diff("page", old, new)

        assert result.old_content == old
        assert result.new_content == new
