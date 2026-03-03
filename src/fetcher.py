"""Async HTTP fetcher for documentation sources."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Self

import httpx

if TYPE_CHECKING:
    from src.config import SourceConfig

# Patterns for dynamic HTML content that changes on every request
_NONCE_ATTR_RE = re.compile(r'\s*nonce="[^"]*"')
# All <script> tags — both inline RSC payloads and src-loaded chunks with per-request hashes
_SCRIPT_TAG_RE = re.compile(r"<script\b[^>]*>.*?</script>|<script\b[^>]*/>", re.DOTALL)
# <link> tags that reference Next.js static assets (CSS/scripts) with per-build hashes
_NEXTJS_LINK_RE = re.compile(
    r'<link\b[^>]*href="/_next/static/[^"]*"[^>]*/?>',
)
# Loading skeleton divs with randomized widths (shimmer placeholders)
_SKELETON_RE = re.compile(r"<div\b[^>]*animate-\[shimmer[^>]*>.*?</div>", re.DOTALL)
# Next.js SSR streaming Suspense placeholders — indicates incomplete server render
_SSR_PLACEHOLDER_RE = re.compile(r'<template\s+id="P:\d+">')


def normalize_html_content(content: str) -> str:
    """Strip dynamic HTML content that changes per-request but carries no doc content.

    Next.js server-rendered pages include several sources of per-request noise:
    1. nonce="..." attributes on <link>/<style> tags (CSP nonces rotate each request)
    2. All <script> tags — RSC payloads reshuffle chunk IDs, and src-loaded chunks
       have content-hashed filenames that change between requests
    3. <link> tags referencing /_next/static/ assets (CSS and script preloads) whose
       content-hashed filenames change between builds/requests
    4. Loading skeleton divs with randomized widths (shimmer animation placeholders)
    """
    result = _SCRIPT_TAG_RE.sub("", content)
    result = _NEXTJS_LINK_RE.sub("", result)
    result = _NONCE_ATTR_RE.sub("", result)
    result = _SKELETON_RE.sub("", result)
    return result


def is_incomplete_ssr(content: str) -> bool:
    """Check if HTML content is an incomplete Next.js SSR streaming response.

    When SSR streaming hasn't finished, the response contains <template id="P:N">
    Suspense placeholders. The actual content for those regions is only available
    in <script> RSC payloads (which we strip during normalization), so saving an
    incomplete response would lose real content and cause false diffs later.
    """
    return bool(_SSR_PLACEHOLDER_RE.search(content))


@dataclass
class FetchResult:
    """Result of fetching a documentation page."""

    page_slug: str
    content: str | None
    status_code: int
    error: str | None = None

    @property
    def is_success(self) -> bool:
        return self.status_code == 200 and self.content is not None


class DocumentFetcher:
    """Async fetcher for documentation from various sources."""

    def __init__(
        self,
        source: SourceConfig,
        timeout: float = 30.0,
    ) -> None:
        self.source = source
        self._client = httpx.AsyncClient(timeout=timeout, follow_redirects=True)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    async def close(self) -> None:
        await self._client.aclose()

    def get_url(self, page_slug: str) -> str:
        """Get URL for a page using source configuration."""
        return self.source.get_url(page_slug)

    async def fetch_page(self, page_slug: str) -> FetchResult:
        """Fetch a single page."""
        url = self.get_url(page_slug)
        try:
            response = await self._client.get(url)
            if response.status_code == 200:
                # Reject HTML responses for .md URLs — indicates a redirect to a
                # rendered page (e.g. consolidated docs) rather than raw markdown
                content_type = response.headers.get("content-type", "")
                if url.endswith(".md") and "text/html" in content_type:
                    return FetchResult(
                        page_slug,
                        None,
                        200,
                        f"Expected markdown but got text/html (likely a redirect to {response.url})",
                    )
                return FetchResult(page_slug, response.text, 200)
            return FetchResult(
                page_slug, None, response.status_code, f"HTTP {response.status_code}"
            )
        except httpx.TimeoutException as e:
            return FetchResult(page_slug, None, 0, f"Connection timed out: {e}")
        except httpx.RequestError as e:
            return FetchResult(page_slug, None, 0, str(e))

    async def fetch_page_with_retry(
        self,
        page_slug: str,
        max_retries: int = 3,
        backoff_base: float = 1.0,
    ) -> FetchResult:
        """Fetch a page with exponential backoff retry."""
        last_result: FetchResult | None = None

        for attempt in range(max_retries):
            result = await self.fetch_page(page_slug)
            if result.is_success:
                return result

            last_result = result

            # Don't retry on 4xx errors (client errors)
            if 400 <= result.status_code < 500:
                return result

            if attempt < max_retries - 1:
                await asyncio.sleep(backoff_base * (2**attempt))

        return last_result or FetchResult(page_slug, None, 0, "Max retries exceeded")

    async def fetch_all(
        self,
        pages: list[str],
        concurrency: int = 5,
        delay: float = 0.5,
    ) -> list[FetchResult]:
        """Fetch multiple pages with rate limiting."""
        semaphore = asyncio.Semaphore(concurrency)

        async def fetch_with_limit(page: str) -> FetchResult:
            async with semaphore:
                result = await self.fetch_page(page)
                if delay > 0:
                    await asyncio.sleep(delay)
                return result

        return await asyncio.gather(*[fetch_with_limit(p) for p in pages])
