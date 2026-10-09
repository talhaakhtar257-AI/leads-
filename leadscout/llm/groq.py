"""Groq via REST (free tier: get a key at https://console.groq.com/keys)."""
from __future__ import annotations

import os

from ..http import client
from .base import LLMError


class Groq:
    name = "groq"

    def __init__(self) -> None:
        self.key = os.environ.get("GROQ_API_KEY") or ""
        self.model = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
        if not self.key:
            raise LLMError("GROQ_API_KEY is not set")

    def generate(self, system: str, prompt: str, max_tokens: int = 1500) -> str:
        body = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": 0.7,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        }
        with client(timeout=90) as c:
            r = c.post("https://api.groq.com/openai/v1/chat/completions", json=body,
                       headers={"Authorization": f"Bearer {self.key}"})
        if r.status_code >= 400:
            raise LLMError(f"Groq error {r.status_code}: {r.text[:300]}")
        return r.json()["choices"][0]["message"]["content"]
