"""Provider-agnostic LLM interface. Pick a provider with `llm:` in campaign.yaml."""
from __future__ import annotations

import json
import os
import re
from typing import Protocol


class LLM(Protocol):
    name: str

    def generate(self, system: str, prompt: str, max_tokens: int = 1500) -> str: ...


class LLMError(RuntimeError):
    pass


def get_llm(name: str = "auto") -> LLM | None:
    """Return a provider, or None for the free template-only mode."""
    if name == "auto":
        if os.environ.get("ANTHROPIC_API_KEY"):
            name = "claude"
        elif os.environ.get("GEMINI_API_KEY"):
            name = "gemini"
        elif os.environ.get("GROQ_API_KEY"):
            name = "groq"
        elif os.environ.get("OLLAMA_MODEL"):
            name = "ollama"
        else:
            return None
    if name == "template":
        return None
    if name == "gemini":
        from .gemini import Gemini
        return Gemini()
    if name == "groq":
        from .groq import Groq
        return Groq()
    if name == "ollama":
        from .ollama import Ollama
        return Ollama()
    if name == "claude":
        from .claude import Claude
        return Claude()
    raise ValueError(f"Unknown llm provider {name!r}")


def parse_json(text: str) -> dict:
    """Pull the first JSON object out of a model response (tolerates ``` fences and chatter)."""
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise LLMError(f"No JSON object in model output: {text[:200]!r}")
    return json.loads(m.group(0))
