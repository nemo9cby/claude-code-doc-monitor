"""Live API test for DiffAnalyzer (skipped unless OPENROUTER_API_KEY is set).

This test exercises the actual OpenRouter API for manual verification.
"""

import os

import pytest

from src.analyzer import DiffAnalyzer
from src.differ import DiffResult


def _mock_diff() -> DiffResult:
    return DiffResult(
        page_slug="test-page",
        has_changes=True,
        old_content="# Old Title\n\nOld content here.",
        new_content="# New Title\n\nNew content here.\n\n## Added Section\n\nThis is new.",
        unified_diff=(
            "@@ -1,3 +1,7 @@\n-# Old Title\n+# New Title\n\n-Old content here.\n+New content here.\n+\n+## Added Section\n+\n+This is new."
        ),
        html_diff="<del># Old Title</del><ins># New Title</ins>",
        added_lines=5,
        removed_lines=2,
        summary="+5 lines, -2 lines",
    )


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.environ.get("OPENROUTER_API_KEY"),
    reason="Requires OPENROUTER_API_KEY env var",
)
async def test_live_analyzer_roundtrip():
    api_key = os.environ["OPENROUTER_API_KEY"]

    analyzer = DiffAnalyzer(
        api_key=api_key,
        model=os.environ.get("OPENROUTER_MODEL", "z-ai/glm-4.7"),
        base_url=os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
    )

    diff = _mock_diff()
    result = await analyzer.analyze_diff(diff)
    assert result is not None
    assert result.page_slug == diff.page_slug
    assert isinstance(result.analysis, str)
    assert len(result.analysis) > 0
