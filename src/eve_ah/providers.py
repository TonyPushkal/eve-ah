"""Small HTTP adapters with bounded retries and sanitized errors."""

import asyncio

import httpx

from eve_ah.config import Settings
from eve_ah.models import EveError


class Provider:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.settings = settings
        self.client = client or httpx.AsyncClient(timeout=settings.timeout)
        self.owns_client = client is None

    async def aclose(self):
        if self.owns_client:
            await self.client.aclose()

    async def generate(self, system: str, user: str) -> str:
        s = self.settings
        key = s.api_key.get_secret_value()
        if s.provider == "gemini":
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/{s.model}:generateContent"
            )
            headers = {"x-goog-api-key": key}
            body = {
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {"maxOutputTokens": s.max_tokens},
            }
        else:
            url = "https://api.openai.com/v1/chat/completions"
            headers = {"Authorization": f"Bearer {key}"}
            body = {
                "model": s.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "max_completion_tokens": s.max_tokens,
            }
        for attempt in range(3):
            try:
                response = await self.client.post(url, headers=headers, json=body)
            except httpx.TimeoutException:
                if attempt == 2:
                    raise EveError(
                        "The model provider timed out. Try again.", 504, "provider_timeout"
                    ) from None
                await asyncio.sleep(0.5 * (2**attempt))
                continue
            except httpx.RequestError:
                if attempt == 2:
                    raise EveError(
                        "Could not reach the model provider.", 502, "provider_connection"
                    ) from None
                await asyncio.sleep(0.5 * (2**attempt))
                continue
            if response.status_code in (401, 403):
                raise EveError(
                    "The provider rejected the configured API key or model access.",
                    502,
                    "provider_auth",
                )
            if response.status_code == 429 or response.status_code >= 500:
                if attempt == 2:
                    raise EveError(
                        "The model provider is busy or unavailable. Try again.",
                        503,
                        "provider_busy",
                    )
                try:
                    delay = max(
                        0, min(float(response.headers.get("retry-after", 0.5 * (2**attempt))), 5)
                    )
                except ValueError:
                    delay = 0.5 * (2**attempt)
                await asyncio.sleep(delay)
                continue
            if not response.is_success:
                raise EveError(
                    "The provider rejected the request. Check the configured model.",
                    502,
                    "provider_request",
                )
            try:
                data = response.json()
                if s.provider == "gemini":
                    candidate = data["candidates"][0]
                    if candidate.get("finishReason") not in (None, "STOP"):
                        raise ValueError("Incomplete or blocked answer")
                    answer = "".join(
                        part.get("text", "")
                        for part in candidate["content"]["parts"]
                        if not part.get("thought")
                    )
                else:
                    choice = data["choices"][0]
                    if choice.get("finish_reason") not in (None, "stop"):
                        raise ValueError("Incomplete or blocked answer")
                    answer = choice["message"]["content"]
                if not isinstance(answer, str) or not answer.strip():
                    raise ValueError("Empty answer")
                return answer.strip()
            except (KeyError, IndexError, TypeError, ValueError, AttributeError):
                raise EveError(
                    "The provider returned no complete usable answer. Try another question or raise EVE_MAX_TOKENS.",
                    502,
                    "provider_output",
                ) from None
        raise EveError("The model provider is unavailable.")
