"""LLM-based diff analyzer using OpenRouter."""

import logging
from dataclasses import dataclass

import httpx

from src.differ import DiffResult

logger = logging.getLogger(__name__)


@dataclass
class AnalysisResult:
    """Result of LLM analysis on a diff."""

    page_slug: str
    analysis: str  # Markdown-formatted analysis text
    source_id: str | None = None
    source_name: str | None = None


class DiffAnalyzer:
    """Analyzes diffs using LLM via OpenRouter API."""

    DEFAULT_MODEL = "z-ai/glm-4.7"
    DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(
        self,
        api_key: str | None,
        model: str | None = None,
        base_url: str | None = None,
    ):
        self.api_key = api_key
        self.model = model or self.DEFAULT_MODEL
        self.base_url = base_url or self.DEFAULT_BASE_URL

    @property
    def enabled(self) -> bool:
        """Check if analyzer is enabled (has API key)."""
        return self.api_key is not None and self.api_key != ""

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
            response = await self._call_api(prompt)
            result = self._parse_response(response, diff.page_slug)
            if not result.analysis:
                logger.warning(f"Empty analysis for {diff.page_slug}")
                return AnalysisResult(
                    page_slug=diff.page_slug,
                    analysis="Analysis returned empty response.",
                )
            return result
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

    async def _call_api(self, prompt: str) -> str:
        """Call the OpenRouter API."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/claude-code-doc-monitor",
                },
                json={
                    "model": self.model,
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a world-class programmer analyzing documentation changes. Provide concise, insightful analysis in markdown format. Focus on what matters to developers.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 4000,  # Higher limit for thinking models
                    "only": ["z-ai"],  # Use z-ai provider
                },
                timeout=120.0,  # Longer timeout for thinking models
            )
            response.raise_for_status()
            data = response.json()
            message = data["choices"][0]["message"]
            # Handle thinking models: prefer content, fall back to reasoning
            content = message.get("content", "")
            if not content and "reasoning" in message:
                content = message["reasoning"]
            return content

    def _parse_response(self, response_text: str, page_slug: str) -> AnalysisResult:
        """Parse LLM response into AnalysisResult."""
        text = response_text.strip() if response_text else ""
        return AnalysisResult(page_slug=page_slug, analysis=text)
