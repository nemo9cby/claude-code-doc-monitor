"""Tests for the LLM analyzer module."""

from unittest.mock import MagicMock, patch

import pytest

from src.analyzer import AnalysisResult, DiffAnalyzer
from src.differ import DiffResult


@pytest.fixture
def sample_diff() -> DiffResult:
    """Create a sample diff for testing."""
    return DiffResult(
        page_slug="setup",
        has_changes=True,
        old_content="## Installation\n\nRun `npm install` to install.\n\n## Configuration",
        new_content="## Installation\n\nRun `npm install` to install dependencies.\n\n### Prerequisites\n\n- Node.js 18+\n- Python 3.12+\n\n## Configuration",
        unified_diff="""--- a/setup.md
+++ b/setup.md
@@ -10,7 +10,10 @@
 ## Installation

-Run `npm install` to install.
+Run `npm install` to install dependencies.
+
+### Prerequisites
+
+- Node.js 18+
+- Python 3.12+

 ## Configuration""",
        html_diff="<div>...</div>",
        added_lines=5,
        removed_lines=2,
        summary="+5 lines, -2 lines",
    )


@pytest.fixture
def analyzer() -> DiffAnalyzer:
    """Create analyzer with test config."""
    return DiffAnalyzer(
        api_key="test-key",
        model="google/gemini-3-flash-preview",
        base_url="https://openrouter.ai/api/v1",
    )


class TestAnalysisResult:
    """Tests for AnalysisResult dataclass."""

    def test_creation(self):
        result = AnalysisResult(
            page_slug="test",
            analysis="**Summary**: Added new section\n- Change 1\n- Change 2",
        )
        assert result.page_slug == "test"
        assert "Summary" in result.analysis
        assert "Change 1" in result.analysis


class TestDiffAnalyzer:
    """Tests for DiffAnalyzer class."""

    def test_init(self, analyzer: DiffAnalyzer):
        assert analyzer.api_key == "test-key"
        assert analyzer.model == "google/gemini-3-flash-preview"
        assert analyzer.base_url == "https://openrouter.ai/api/v1"

    def test_init_defaults(self):
        analyzer = DiffAnalyzer(api_key="key")
        # No hardcoded defaults; requires config
        assert analyzer.model is None
        assert analyzer.base_url is None
        assert analyzer.enabled is False

    def test_disabled_when_no_key(self):
        analyzer = DiffAnalyzer(api_key=None)
        assert analyzer.enabled is False

    def test_enabled_when_key_provided(self, analyzer: DiffAnalyzer):
        assert analyzer.enabled is True

    @pytest.mark.asyncio
    async def test_analyze_diff_success(self, analyzer: DiffAnalyzer, sample_diff: DiffResult):
        mock_response = {
            "choices": [
                {
                    "message": {
                        "content": "**Summary**: Added prerequisites section.\n\n**Key Changes**:\n- Added Node.js requirement\n- Added Python requirement\n\n**Impact**: Low"
                    }
                }
            ]
        }

        with patch("requests.post") as mock_post:
            mock_post.return_value = MagicMock(
                status_code=200,
                json=lambda: mock_response,
                raise_for_status=lambda: None,
            )

            result = await analyzer.analyze_diff(sample_diff)

            assert result.page_slug == "setup"
            assert "prerequisites" in result.analysis.lower()
            assert "Node.js" in result.analysis

    @pytest.mark.asyncio
    async def test_analyze_diff_api_error(self, analyzer: DiffAnalyzer, sample_diff: DiffResult):
        import requests as req

        with patch("requests.post") as mock_post:
            mock_post.side_effect = req.RequestException("API Error")

            result = await analyzer.analyze_diff(sample_diff)

            assert result.page_slug == "setup"
            assert "error" in result.analysis.lower()

    @pytest.mark.asyncio
    async def test_analyze_diff_disabled(self, sample_diff: DiffResult):
        analyzer = DiffAnalyzer(api_key=None)
        result = await analyzer.analyze_diff(sample_diff)

        assert result is None

    @pytest.mark.asyncio
    async def test_analyze_multiple_diffs(self, analyzer: DiffAnalyzer, sample_diff: DiffResult):
        diff2 = DiffResult(
            page_slug="config",
            has_changes=True,
            old_content="old",
            new_content="new content here",
            unified_diff="...",
            html_diff="...",
            added_lines=10,
            removed_lines=0,
            summary="+10 lines",
        )

        mock_response = {
            "choices": [
                {
                    "message": {
                        "content": "**Summary**: Test summary\n\n**Key Changes**:\n- Change 1"
                    }
                }
            ]
        }

        with patch("requests.post") as mock_post:
            mock_post.return_value = MagicMock(
                status_code=200,
                json=lambda: mock_response,
                raise_for_status=lambda: None,
            )

            results = await analyzer.analyze_all([sample_diff, diff2])

            assert len(results) == 2
            assert results[0].page_slug == "setup"
            assert results[1].page_slug == "config"

    @pytest.mark.asyncio
    async def test_analyze_skips_no_changes(self, analyzer: DiffAnalyzer):
        diff = DiffResult(
            page_slug="unchanged",
            has_changes=False,
            old_content="same",
            new_content="same",
            unified_diff="",
            html_diff="",
            added_lines=0,
            removed_lines=0,
            summary="No changes",
        )

        results = await analyzer.analyze_all([diff])
        assert len(results) == 0

    def test_build_prompt(self, analyzer: DiffAnalyzer, sample_diff: DiffResult):
        prompt = analyzer._build_prompt(sample_diff)

        assert "setup" in prompt
        assert sample_diff.unified_diff in prompt
        assert "markdown" in prompt.lower()

    def test_parse_response(self, analyzer: DiffAnalyzer):
        response_text = "**Summary**: Test change\n\n**Impact**: Low"

        result = analyzer._parse_response(response_text, "test-page")

        assert result.page_slug == "test-page"
        assert result.analysis == response_text

    def test_parse_response_empty(self, analyzer: DiffAnalyzer):
        result = analyzer._parse_response("", "test-page")

        assert result.page_slug == "test-page"
        assert result.analysis == ""

    @pytest.mark.asyncio
    async def test_analyze_empty_response(self, analyzer: DiffAnalyzer, sample_diff: DiffResult):
        mock_response = {"choices": [{"message": {"content": ""}}]}

        with patch("requests.post") as mock_post:
            mock_post.return_value = MagicMock(
                status_code=200,
                json=lambda: mock_response,
                raise_for_status=lambda: None,
            )

            result = await analyzer.analyze_diff(sample_diff)

            assert result.page_slug == "setup"
            assert "empty" in result.analysis.lower()
