"""E2E test fixtures for the documentation monitoring pipeline."""

import asyncio
import os
import shutil
import threading
from collections.abc import Generator
from pathlib import Path

import pytest
from aiohttp import web

# Paths
E2E_DIR = Path(__file__).parent
FIXTURES_DIR = E2E_DIR / "fixtures"
TEST_OUTPUT_DIR = E2E_DIR / ".test_output"


@pytest.fixture(scope="module")
def test_output_dir() -> Generator[Path, None, None]:
    """Create and cleanup isolated test output directory."""
    # Clean up before test (in case previous run failed)
    if TEST_OUTPUT_DIR.exists():
        shutil.rmtree(TEST_OUTPUT_DIR)

    TEST_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (TEST_OUTPUT_DIR / "docs" / "test").mkdir(parents=True, exist_ok=True)
    (TEST_OUTPUT_DIR / "reports").mkdir(parents=True, exist_ok=True)

    yield TEST_OUTPUT_DIR

    # Cleanup after all E2E tests (unless PRESERVE_E2E_OUTPUT is set)
    if os.environ.get("PRESERVE_E2E_OUTPUT"):
        print(f"\n📁 Test output preserved at: {TEST_OUTPUT_DIR}")
    elif TEST_OUTPUT_DIR.exists():
        shutil.rmtree(TEST_OUTPUT_DIR)


class ContentServer:
    """Mutable content server that can switch between v1 and v2."""

    def __init__(self) -> None:
        self.version = "v1"

    def set_version(self, version: str) -> None:
        """Switch content version (v1 or v2)."""
        self.version = version

    def get_content(self, slug: str) -> str | None:
        """Get content for a page slug."""
        file_path = FIXTURES_DIR / f"test_pages_{self.version}" / f"{slug}.md"
        if file_path.exists():
            return file_path.read_text()
        return None


# Global content server instance (shared across all tests)
_content_server = ContentServer()


@pytest.fixture(scope="module")
def content_server() -> ContentServer:
    """Mutable content server instance."""
    return _content_server


def _run_server(loop: asyncio.AbstractEventLoop, started_event: threading.Event) -> None:
    """Run the aiohttp server in a background thread."""
    asyncio.set_event_loop(loop)

    async def handle_markdown(request: web.Request) -> web.Response:
        slug = request.match_info["slug"]
        content = _content_server.get_content(slug)

        if content is not None:
            return web.Response(text=content, content_type="text/markdown")
        return web.Response(status=404, text=f"Page not found: {slug}")

    async def start_server() -> web.AppRunner:
        app = web.Application()
        app.router.add_get("/test-docs/test/{slug}.md", handle_markdown)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "localhost", 8765)
        await site.start()
        return runner

    runner = loop.run_until_complete(start_server())
    started_event.set()

    try:
        loop.run_forever()
    finally:
        loop.run_until_complete(runner.cleanup())


@pytest.fixture(scope="module")
def test_http_server() -> Generator[str, None, None]:
    """Start local HTTP server serving test markdown files in a background thread."""
    loop = asyncio.new_event_loop()
    started_event = threading.Event()

    server_thread = threading.Thread(target=_run_server, args=(loop, started_event), daemon=True)
    server_thread.start()

    # Wait for server to start
    started_event.wait(timeout=5.0)

    yield "http://localhost:8765"

    # Stop the server
    loop.call_soon_threadsafe(loop.stop)
