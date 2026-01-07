"""LLM-based analyzers using OpenRouter.

Provides per-diff and per-batch analysis helpers.
Uses requests library for more robust HTTP handling per OpenRouter recommendations.
"""

import asyncio
import logging
import time
from collections.abc import Iterable
from dataclasses import dataclass

import requests

from src.differ import DiffResult

logger = logging.getLogger(__name__)


@dataclass
class AnalysisResult:
    """Result of LLM analysis on a diff."""

    page_slug: str
    analysis: str  # Markdown-formatted analysis text
    reasoning: str = ""  # Model reasoning/thinking (if available)
    source_id: str | None = None
    source_name: str | None = None


class DiffAnalyzer:
    """Analyzes diffs using LLM via OpenRouter API.

    Note: Avoids hardcoded model defaults. Pass model/base_url via config.
    """

    def __init__(
        self,
        api_key: str | None,
        model: str | None = None,
        base_url: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        timeout_seconds: float | None = None,
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.temperature = 0.3 if temperature is None else temperature
        self.max_tokens = 2000 if max_tokens is None else max_tokens
        self.timeout_seconds = 120.0 if timeout_seconds is None else timeout_seconds

    @property
    def enabled(self) -> bool:
        """Check if analyzer is enabled (has API key and configuration)."""
        return (
            self.api_key is not None
            and self.api_key != ""
            and self.model is not None
            and self.base_url is not None
        )

    async def analyze_diff(self, diff: DiffResult) -> AnalysisResult | None:
        """Analyze a single diff using LLM.

        Returns None if analyzer is disabled.
        """
        if not self.enabled:
            return None

        if not diff.has_changes:
            return None

        try:
            prompt = self._build_prompt(diff)
            content, reasoning = await self._call_api(prompt)
            if not content:
                logger.warning(f"Empty analysis for {diff.page_slug}")
                return AnalysisResult(
                    page_slug=diff.page_slug,
                    analysis="Analysis returned empty response.",
                )
            return AnalysisResult(
                page_slug=diff.page_slug,
                analysis=content.strip(),
                reasoning=reasoning.strip() if reasoning else "",
            )
        except Exception as e:
            logger.error(f"Error analyzing diff for {diff.page_slug}: {e}")
            return AnalysisResult(
                page_slug=diff.page_slug,
                analysis=f"Analysis error: {str(e)[:100]}",
            )

    async def analyze_all(self, diffs: list[DiffResult]) -> list[AnalysisResult]:
        """Analyze multiple diffs.

        Only analyzes diffs with changes.
        """
        results = []
        for diff in diffs:
            if diff.has_changes:
                result = await self.analyze_diff(diff)
                if result:
                    results.append(result)
        return results

    async def analyze_batch(self, diffs: Iterable[DiffResult]) -> AnalysisResult | None:
        """Analyze a batch of diffs and return a single summary.

        Returns None if analyzer is disabled or there are no changed diffs.
        """
        if not self.enabled:
            return None

        changed = [d for d in diffs if d.has_changes]
        if not changed:
            return None

        try:
            prompt = self._build_batch_prompt(changed)
            content, reasoning = await self._call_api(prompt)
            if not content:
                logger.warning("Empty batch analysis response")
                return AnalysisResult(
                    page_slug="__batch__", analysis="Analysis returned empty response."
                )
            return AnalysisResult(
                page_slug="__batch__",
                analysis=content.strip(),
                reasoning=reasoning.strip() if reasoning else "",
            )
        except Exception as e:
            logger.error(f"Error analyzing batch: {e}")
            return AnalysisResult(page_slug="__batch__", analysis=f"Analysis error: {str(e)[:100]}")

    def _build_prompt(self, diff: DiffResult) -> str:
        """Build the prompt for LLM analysis."""
        return f"""You are a world-class programmer with deep expertise in developer tools and documentation. Analyze this documentation change and explain what changed and why it matters to developers.

Page: {diff.page_slug}.md
Lines added: {diff.added_lines} | Lines removed: {diff.removed_lines}

Diff:
```
{diff.unified_diff}
```

Provide a concise analysis in markdown format:
1. **Summary**: 1-2 sentences on what changed
2. **Key Changes**: Bullet points of specific changes (max 5)
3. **Impact**: Is this low (typos), medium (improved docs), high (new features), or breaking?
        
Focus on implications for developers. Be concise and insightful."""

    def _build_batch_prompt(self, diffs: list[DiffResult]) -> str:
        """Build a prompt to analyze a batch of changes across pages."""
        lines = [
            "You are a world-class programmer with deep expertise in developer tools and documentation.",
            "Analyze the following documentation changes as a single batch and summarize what changed and why it matters to developers.",
            "",
            f"Total changed pages: {len(diffs)}",
            "",
        ]
        for d in diffs[:25]:  # cap to avoid overly long prompts
            lines.append(f"Page: {d.page_slug}.md | +{d.added_lines} / -{d.removed_lines}")
            lines.append("Diff:\n```\n" + (d.unified_diff or "")[:8000] + "\n```\n")
        lines.append(
            "Provide a concise batch analysis in markdown format:\n"
            "1. Overall Summary (1-2 sentences)\n"
            "2. Key Themes across pages (bullets)\n"
            "3. Impact level (Low/Medium/High/Breaking) with reasoning\n"
            "4. Action items for developers (bullets, max 5)"
        )
        return "\n".join(lines)

    def _call_api_sync(self, payload: dict, headers: dict) -> str:
        """Synchronous API call with retries using requests library.

        Uses requests instead of httpx for more robust HTTP handling,
        especially with OpenRouter's chunked transfer encoding.
        """
        max_attempts = 3
        last_exc: Exception | None = None

        for attempt in range(1, max_attempts + 1):
            try:
                response = requests.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=self.timeout_seconds,
                )
                response.raise_for_status()
                data = response.json()
                message = data["choices"][0]["message"]
                logger.debug(f"API response message keys: {message.keys()}")
                logger.debug(f"API response content: {repr(message.get('content', ''))[:100]}")
                logger.debug(f"API response reasoning: {repr(message.get('reasoning', ''))[:100]}")
                content = message.get("content", "")
                reasoning = message.get("reasoning", "")
                # If content is empty but reasoning exists, use reasoning as content
                if not content and reasoning:
                    logger.info("Using reasoning field as content was empty")
                    content = reasoning
                    reasoning = ""  # Don't duplicate
                # Return as tuple: (content, reasoning)
                return (content, reasoning)
            except requests.RequestException as e:
                last_exc = e
                logger.warning(
                    f"Request error on attempt {attempt}/{max_attempts}: {e}. Retrying..."
                )
                if attempt < max_attempts:
                    time.sleep(0.5 * attempt)

        assert last_exc is not None
        raise last_exc

    async def _call_api(self, prompt: str) -> str:
        """Call the OpenRouter API asynchronously.

        Wraps the sync requests call in asyncio.to_thread() for async compatibility.
        """
        if not self.model or not self.base_url:
            raise RuntimeError("Analyzer not configured with model/base_url")

        # Adjust defaults for GLM-4.7 specifically
        model_lower = self.model.lower()
        is_glm47 = "glm-4.7" in model_lower or "glm4.7" in model_lower
        max_tokens = min(self.max_tokens, 1200) if is_glm47 else self.max_tokens

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a world-class programmer analyzing documentation changes. "
                        "Provide concise, insightful analysis in markdown format. "
                        "Focus on what matters to developers."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": self.temperature,
            "max_tokens": max_tokens,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            # Helps attribution per OpenRouter recommendation
            "HTTP-Referer": "https://github.com/claude-code-doc-monitor",
            # Optional title for dashboards
            "X-Title": "Doc Monitor AI Analysis",
        }

        return await asyncio.to_thread(self._call_api_sync, payload, headers)
