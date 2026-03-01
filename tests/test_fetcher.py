"""Tests for fetcher module."""

from pathlib import Path

import httpx
import pytest
import respx

from src.config import SourceConfig
from src.fetcher import DocumentFetcher, FetchResult, normalize_html_content


class TestNormalizeHtmlContent:
    def test_strips_nonce_attributes(self) -> None:
        html = '<link rel="stylesheet" href="/style.css" nonce="abc123==" data-precedence="next"/>'
        result = normalize_html_content(html)
        assert "nonce=" not in result
        assert 'href="/style.css"' in result

    def test_strips_multiple_nonces(self) -> None:
        html = (
            '<script src="/a.js" nonce="token1"></script>'
            '<script src="/b.js" nonce="token2"></script>'
        )
        result = normalize_html_content(html)
        assert "nonce=" not in result
        assert 'src="/a.js"' in result
        assert 'src="/b.js"' in result

    def test_identical_after_normalization(self) -> None:
        """Two fetches with different nonces should normalize to the same content."""
        html_v1 = '<link href="/s.css" nonce="AAA==" /><script src="/a.js" nonce="AAA=="></script>'
        html_v2 = '<link href="/s.css" nonce="BBB==" /><script src="/a.js" nonce="BBB=="></script>'
        assert normalize_html_content(html_v1) == normalize_html_content(html_v2)

    def test_preserves_non_html_content(self) -> None:
        markdown = "# Hello\n\nThis is markdown content."
        assert normalize_html_content(markdown) == markdown

    def test_preserves_real_content_changes(self) -> None:
        """Content changes beyond nonces should still be detected."""
        html_v1 = '<div nonce="AAA==">Old content</div>'
        html_v2 = '<div nonce="BBB==">New content</div>'
        n1 = normalize_html_content(html_v1)
        n2 = normalize_html_content(html_v2)
        assert n1 != n2
        assert "Old content" in n1
        assert "New content" in n2


class TestFetchResult:
    def test_success_result(self) -> None:
        result = FetchResult(page_slug="overview", content="# Overview", status_code=200)
        assert result.page_slug == "overview"
        assert result.content == "# Overview"
        assert result.status_code == 200
        assert result.error is None
        assert result.is_success is True

    def test_error_result(self) -> None:
        result = FetchResult(page_slug="missing", content=None, status_code=404, error="Not Found")
        assert result.page_slug == "missing"
        assert result.content is None
        assert result.status_code == 404
        assert result.error == "Not Found"
        assert result.is_success is False


class TestDocumentFetcher:
    @pytest.fixture
    def docs_source(self) -> SourceConfig:
        return SourceConfig(
            id="test",
            name="Test",
            docs_dir=Path("docs/test"),
            pages_file=Path("config/pages/test.yaml"),
            source_type="docs",
            base_url="https://example.com/docs",
            language="en",
        )

    @pytest.fixture
    def github_source(self) -> SourceConfig:
        return SourceConfig(
            id="github-test",
            name="GitHub Test",
            docs_dir=Path("docs/github-test"),
            pages_file=Path("config/pages/github-test.yaml"),
            source_type="github",
            github_owner="anthropics",
            github_repo="claude-code",
            github_branch="main",
        )

    @pytest.fixture
    def fetcher(self, docs_source: SourceConfig) -> DocumentFetcher:
        return DocumentFetcher(source=docs_source)

    def test_get_url_docs(self, fetcher: DocumentFetcher) -> None:
        url = fetcher.get_url("overview")
        assert url == "https://example.com/docs/en/overview.md"

    def test_get_url_github(self, github_source: SourceConfig) -> None:
        fetcher = DocumentFetcher(source=github_source)
        url = fetcher.get_url("CHANGELOG.md")
        assert url == "https://raw.githubusercontent.com/anthropics/claude-code/main/CHANGELOG.md"

    @respx.mock
    async def test_fetch_page_success(self, fetcher: DocumentFetcher) -> None:
        respx.get("https://example.com/docs/en/overview.md").mock(
            return_value=httpx.Response(200, text="# Overview\n\nWelcome!")
        )

        result = await fetcher.fetch_page("overview")

        assert result.is_success is True
        assert result.page_slug == "overview"
        assert result.content == "# Overview\n\nWelcome!"
        assert result.status_code == 200
        assert result.error is None

    @respx.mock
    async def test_fetch_page_not_found(self, fetcher: DocumentFetcher) -> None:
        respx.get("https://example.com/docs/en/missing.md").mock(return_value=httpx.Response(404))

        result = await fetcher.fetch_page("missing")

        assert result.is_success is False
        assert result.page_slug == "missing"
        assert result.content is None
        assert result.status_code == 404
        assert result.error == "HTTP 404"

    @respx.mock
    async def test_fetch_page_timeout(self, fetcher: DocumentFetcher) -> None:
        respx.get("https://example.com/docs/en/slow.md").mock(
            side_effect=httpx.TimeoutException("Connection timed out")
        )

        result = await fetcher.fetch_page("slow")

        assert result.is_success is False
        assert result.page_slug == "slow"
        assert result.content is None
        assert result.status_code == 0
        assert "timed out" in result.error.lower()

    @respx.mock
    async def test_fetch_all_pages(self, fetcher: DocumentFetcher) -> None:
        respx.get("https://example.com/docs/en/page1.md").mock(
            return_value=httpx.Response(200, text="# Page 1")
        )
        respx.get("https://example.com/docs/en/page2.md").mock(
            return_value=httpx.Response(200, text="# Page 2")
        )
        respx.get("https://example.com/docs/en/page3.md").mock(return_value=httpx.Response(404))

        results = await fetcher.fetch_all(["page1", "page2", "page3"], concurrency=2, delay=0.0)

        assert len(results) == 3
        slugs = {r.page_slug for r in results}
        assert slugs == {"page1", "page2", "page3"}

        success_count = sum(1 for r in results if r.is_success)
        assert success_count == 2

    @respx.mock
    async def test_fetch_with_retry(self, fetcher: DocumentFetcher) -> None:
        # First call fails, second succeeds
        route = respx.get("https://example.com/docs/en/flaky.md")
        route.side_effect = [
            httpx.Response(500),
            httpx.Response(200, text="# Flaky page"),
        ]

        result = await fetcher.fetch_page_with_retry("flaky", max_retries=2)

        assert result.is_success is True
        assert result.content == "# Flaky page"
        assert route.call_count == 2

    async def test_close(self, fetcher: DocumentFetcher) -> None:
        await fetcher.close()
        assert fetcher._client.is_closed

    async def test_context_manager(self, docs_source: SourceConfig) -> None:
        async with DocumentFetcher(source=docs_source) as fetcher:
            assert not fetcher._client.is_closed
        assert fetcher._client.is_closed
