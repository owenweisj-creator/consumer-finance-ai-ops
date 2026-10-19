from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

import requests

from src.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL


class LLMError(RuntimeError):
    pass


@dataclass
class LLMResponse:
    content: str
    latency_ms: int
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    model: str | None = None


class DeepSeekClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: int = 90,
    ) -> None:
        self.api_key = api_key or DEEPSEEK_API_KEY
        self.base_url = (base_url or DEEPSEEK_BASE_URL).rstrip("/")
        self.model = model or DEEPSEEK_MODEL
        self.timeout = timeout
        if not self.api_key:
            raise LLMError("DEEPSEEK_API_KEY is not configured. Create a local .env file.")

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int = 1500,
        json_mode: bool = False,
        retries: int = 2,
    ) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        last_error: Exception | None = None
        for attempt in range(retries + 1):
            started = time.perf_counter()
            try:
                response = requests.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=self.timeout,
                )
                if response.status_code >= 400:
                    raise LLMError(f"DeepSeek HTTP {response.status_code}: {response.text[:300]}")
                body = response.json()
                choice = body["choices"][0]["message"]["content"]
                usage = body.get("usage", {})
                return LLMResponse(
                    content=choice,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    prompt_tokens=usage.get("prompt_tokens"),
                    completion_tokens=usage.get("completion_tokens"),
                    model=body.get("model"),
                )
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt < retries:
                    time.sleep(1.5 * (attempt + 1))
        raise LLMError(f"DeepSeek request failed after retries: {last_error}")

    def chat_json(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int = 1500,
    ) -> tuple[dict[str, Any], LLMResponse]:
        response = self.chat(messages, temperature=temperature, max_tokens=max_tokens, json_mode=True)
        text = response.content.strip()
        try:
            return json.loads(text), response
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                return json.loads(text[start : end + 1]), response
            raise LLMError(f"Model did not return valid JSON: {text[:300]}")

    def ping(self) -> dict[str, Any]:
        response = self.chat(
            [{"role": "user", "content": "只回复 OK 两个字母。"}],
            temperature=0.0,
            max_tokens=10,
        )
        return {"ok": "OK" in response.content.upper(), "content": response.content, "latency_ms": response.latency_ms}
