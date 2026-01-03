"""Tests for fetcher module."""

import httpx
import pytest
import respx

from src.fetcher import DocumentFetcher, FetchResult


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
    def fetcher(self) -> DocumentFetcher:
        return DocumentFetcher(base_url="https://example.com/docs", language="en")

    def test_get_markdown_url(self, fetcher: DocumentFetcher) -> None:
        url = fetcher.get_markdown_url("overview")
        assert url == "https://example.com/docs/en/overview.md"

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

    async def test_context_manager(self) -> None:
        async with DocumentFetcher("https://example.com/docs", "en") as fetcher:
            assert not fetcher._client.is_closed
        assert fetcher._client.is_closed
