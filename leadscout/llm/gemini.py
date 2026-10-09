"""Google Gemini via REST (free tier: get a key at https://aistudio.google.com/apikey)."""
from __future__ import annotations

import os

from ..http import client
from .base import LLMError


class Gemini:
    name = "gemini"

    def __init__(self) -> None:
        self.key = os.environ.get("GEMINI_API_KEY") or ""
        self.model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
        if not self.key:
            raise LLMError("GEMINI_API_KEY is not set")

    def generate(self, system: str, prompt: str, max_tokens: int = 1500) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.7},
        }
        with client(timeout=90) as c:
            r = c.post(url, json=body, headers={"x-goog-api-key": self.key})
        if r.status_code >= 400:
            raise LLMError(f"Gemini error {r.status_code}: {r.text[:300]}")
        try:
            parts = r.json()["candidates"][0]["content"]["parts"]
        except (KeyError, IndexError) as e:
            raise LLMError(f"Unexpected Gemini response: {r.text[:300]}") from e
        return "".join(p.get("text", "") for p in parts)
