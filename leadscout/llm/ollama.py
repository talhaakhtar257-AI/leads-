"""Local models via Ollama (free, runs on your machine: https://ollama.com)."""
from __future__ import annotations

import os

import httpx

from ..http import client
from .base import LLMError


class Ollama:
    name = "ollama"

    def __init__(self) -> None:
        self.model = os.environ.get("OLLAMA_MODEL", "llama3.1")
        self.host = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")

    def generate(self, system: str, prompt: str, max_tokens: int = 1500) -> str:
        body = {
            "model": self.model,
            "stream": False,
            "options": {"num_predict": max_tokens},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        }
        try:
            with client(timeout=300) as c:
                r = c.post(f"{self.host}/api/chat", json=body)
        except httpx.HTTPError as e:
            raise LLMError(f"Cannot reach Ollama at {self.host}: {e}") from e
        if r.status_code >= 400:
            raise LLMError(f"Ollama error {r.status_code}: {r.text[:300]}")
        return r.json()["message"]["content"]
