"""Async HTTP fetcher for documentation sources."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Self

import httpx

if TYPE_CHECKING:
    from src.config import SourceConfig


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
