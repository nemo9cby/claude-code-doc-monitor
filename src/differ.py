"""Diff engine for comparing documentation versions."""

import difflib
from dataclasses import dataclass

from diff_match_patch import diff_match_patch


@dataclass
class DiffResult:
    """Result of comparing two document versions."""

    page_slug: str
    has_changes: bool
    old_content: str
    new_content: str
    unified_diff: str
    html_diff: str
    added_lines: int
    removed_lines: int
    summary: str


class DocumentDiffer:
    """Compare old and new document content."""

    def __init__(self) -> None:
        self._dmp = diff_match_patch()

    def compute_diff(self, page_slug: str, old_content: str, new_content: str) -> DiffResult:
        """Compute diff between old and new content."""
        has_changes = old_content != new_content

        if not has_changes:
            return DiffResult(
                page_slug=page_slug,
                has_changes=False,
                old_content=old_content,
                new_content=new_content,
                unified_diff="",
                html_diff="",
                added_lines=0,
                removed_lines=0,
                summary="No changes",
            )

        unified_diff = self._compute_unified_diff(page_slug, old_content, new_content)
        html_diff = self._compute_html_diff(old_content, new_content)
        added, removed = self._count_changes(old_content, new_content)
        summary = self._generate_summary(added, removed)

        return DiffResult(
            page_slug=page_slug,
            has_changes=True,
            old_content=old_content,
            new_content=new_content,
            unified_diff=unified_diff,
            html_diff=html_diff,
            added_lines=added,
            removed_lines=removed,
            summary=summary,
        )

    def _compute_unified_diff(self, page_slug: str, old_content: str, new_content: str) -> str:
        """Generate unified diff format."""
        old_lines = old_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)

        diff = difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{page_slug}.md",
            tofile=f"b/{page_slug}.md",
        )
        return "".join(diff)

    def _compute_html_diff(self, old_content: str, new_content: str) -> str:
        """Generate HTML diff using diff-match-patch."""
        diffs = self._dmp.diff_main(old_content, new_content)
        self._dmp.diff_cleanupSemantic(diffs)
        return self._dmp.diff_prettyHtml(diffs)

    def _count_changes(self, old_content: str, new_content: str) -> tuple[int, int]:
        """Count added and removed lines."""
        old_lines = set(old_content.splitlines())
        new_lines = set(new_content.splitlines())

        added = len(new_lines - old_lines)
        removed = len(old_lines - new_lines)

        return added, removed

    def _generate_summary(self, added: int, removed: int) -> str:
        """Generate a human-readable summary."""
        if added == 0 and removed == 0:
            return "Formatting changes"

        parts = []
        if added > 0:
            parts.append(f"+{added} lines")
        if removed > 0:
            parts.append(f"-{removed} lines")

        return ", ".join(parts)
