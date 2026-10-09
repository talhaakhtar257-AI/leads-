"""Anthropic Claude (paid, best writing quality). `pip install "leadscout[claude]"` and set ANTHROPIC_API_KEY."""
from __future__ import annotations

import os

from .base import LLMError


class Claude:
    name = "claude"

    def __init__(self) -> None:
        try:
            import anthropic
        except ImportError as e:
            raise LLMError('Install the Claude extra: pip install "leadscout[claude]"') from e
        self._anthropic = anthropic
        self.client = anthropic.Anthropic()
        self.model = os.environ.get("CLAUDE_MODEL", "claude-opus-5-5")

    def generate(self, system: str, prompt: str, max_tokens: int = 1500) -> str:
        try:
            # Short copywriting task: low effort keeps cost down. The server-side
            # fallback beta retries on another model if a request is refused.
            response = self.client.beta.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
                output_config={"effort": "low"},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except self._anthropic.APIStatusError as e:
            raise LLMError(f"Claude API error {e.status_code}: {e.message}") from e
        except self._anthropic.APIConnectionError as e:
            raise LLMError(f"Cannot reach Claude API: {e}") from e
        if response.stop_reason == "refusal":
            raise LLMError("Claude declined this request")
        return "".join(b.text for b in response.content if b.type == "text")
