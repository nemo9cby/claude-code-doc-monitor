"""Tests for fetcher module."""

from pathlib import Path

import httpx
import pytest
import respx

from src.config import SourceConfig
from src.fetcher import DocumentFetcher, FetchResult, is_incomplete_ssr, normalize_html_content


class TestNormalizeHtmlContent:
    def test_strips_nonce_attributes(self) -> None:
        html = '<link rel="stylesheet" href="/style.css" nonce="abc123==" data-precedence="next"/>'
        result = normalize_html_content(html)
        assert "nonce=" not in result
        assert 'href="/style.css"' in result

    def test_strips_multiple_nonces(self) -> None:
        html = (
            '<link href="/a.css" nonce="token1" data-precedence="next"/>'
            '<link href="/b.css" nonce="token2" data-precedence="next"/>'
        )
        result = normalize_html_content(html)
        assert "nonce=" not in result
        assert 'href="/a.css"' in result
        assert 'href="/b.css"' in result

    def test_identical_after_normalization(self) -> None:
        """Two fetches with different nonces should normalize to the same content."""
        html_v1 = '<link href="/s.css" nonce="AAA==" /><link href="/b.css" nonce="AAA==" />'
        html_v2 = '<link href="/s.css" nonce="BBB==" /><link href="/b.css" nonce="BBB==" />'
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

    def test_strips_rsc_script_tags(self) -> None:
        """Next.js RSC payload scripts should be stripped entirely."""
        html = (
            "<div>Real content</div>"
            '<script>self.__next_f.push([1,"17:I[215187218,[\\"13263\\"]"])</script>'
            '<script>self.__next_f.push([1,"18:I[7664339605,[\\"chunk\\"]"])</script>'
            "<p>More content</p>"
        )
        result = normalize_html_content(html)
        assert "self.__next_f" not in result
        assert "Real content" in result
        assert "More content" in result

    def test_rsc_chunk_id_reorder_normalizes_equal(self) -> None:
        """Same RSC content with reshuffled chunk IDs should normalize identically."""
        html_v1 = (
            "<div>Content</div>"
            '<script>self.__next_f.push([1,"17:I[215187218,[\\"x\\"]"])</script>'
            '<script>self.__next_f.push([1,"18:I[7664339605,[\\"y\\"]"])</script>'
        )
        html_v2 = (
            "<div>Content</div>"
            '<script>self.__next_f.push([1,"19:I[215187218,[\\"x\\"]"])</script>'
            '<script>self.__next_f.push([1,"1a:I[7664339605,[\\"y\\"]"])</script>'
        )
        assert normalize_html_content(html_v1) == normalize_html_content(html_v2)

    def test_strips_all_script_tags(self) -> None:
        """All script tags should be stripped (both inline and src-loaded)."""
        html = (
            "<div>Content</div>"
            '<script src="/_next/static/chunks/82418-96ce9b0bba7975e1.js" async=""></script>'
            '<script>console.log("inline")</script>'
        )
        result = normalize_html_content(html)
        assert "<script" not in result
        assert "Content" in result

    def test_strips_nextjs_static_links(self) -> None:
        """<link> tags referencing /_next/static/ assets should be stripped."""
        html = (
            '<link rel="preload" as="script" fetchPriority="low" href="/_next/static/chunks/webpack-abc123.js"/>'
            '<link rel="stylesheet" href="/_next/static/css/b2961405e21ace61.css" data-precedence="next"/>'
            '<link rel="stylesheet" href="/custom/style.css" data-precedence="next"/>'
        )
        result = normalize_html_content(html)
        assert "webpack" not in result
        assert "b2961405" not in result
        assert "custom/style.css" in result

    def test_css_hash_change_normalizes_equal(self) -> None:
        """CSS files with different content hashes should normalize identically."""
        html_v1 = '<link rel="stylesheet" href="/_next/static/css/b2961405e21ace61.css" data-precedence="next"/><div>Content</div>'
        html_v2 = '<link rel="stylesheet" href="/_next/static/css/c40933516c29a5e3.css" data-precedence="next"/><div>Content</div>'
        assert normalize_html_content(html_v1) == normalize_html_content(html_v2)

    def test_strips_skeleton_loading_divs(self) -> None:
        """Shimmer skeleton placeholders with random widths should be stripped."""
        html_v1 = (
            "<div>Real content</div>"
            '<div class="relative bg-bg-400 overflow-hidden after:animate-[shimmer_1.5s_infinite]"'
            ' style="height:32px;width:214px"><span class="sr-only">Loading...</span></div>'
        )
        html_v2 = (
            "<div>Real content</div>"
            '<div class="relative bg-bg-400 overflow-hidden after:animate-[shimmer_1.5s_infinite]"'
            ' style="height:32px;width:313px"><span class="sr-only">Loading...</span></div>'
        )
        assert normalize_html_content(html_v1) == normalize_html_content(html_v2)
        assert "Real content" in normalize_html_content(html_v1)


class TestIsIncompleteSsr:
    def test_detects_suspense_placeholder(self) -> None:
        html = '<div>Content</div><template id="P:2"></template><div>More</div>'
        assert is_incomplete_ssr(html) is True

    def test_detects_multiple_placeholders(self) -> None:
        html = '<template id="P:2"></template><template id="P:3"></template>'
        assert is_incomplete_ssr(html) is True

    def test_ignores_boundary_templates(self) -> None:
        """B: templates are boundary markers, not Suspense placeholders."""
        html = '<template id="B:0"></template><div>Full content here</div>'
        assert is_incomplete_ssr(html) is False

    def test_complete_ssr_response(self) -> None:
        html = "<div>Fully rendered content</div><p>No placeholders</p>"
        assert is_incomplete_ssr(html) is False

    def test_non_html_content(self) -> None:
        markdown = "# Hello\n\nMarkdown content"
        assert is_incomplete_ssr(markdown) is False


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
