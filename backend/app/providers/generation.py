import json
from typing import Protocol

from app.core.errors import ProviderUnavailable
from app.core.logging import log_stage


class GenerationProvider(Protocol):
    name: str

    async def generate_json(self, prompt: str, *, request_id: str) -> dict: ...


class StubGenerationProvider:
    """Deterministic provider for tests. Makes the whole pipeline testable with
    no network and no API keys, so CI needs no secrets."""

    name = "stub"

    def __init__(self, responses: list[dict]) -> None:
        self._responses = list(responses)
        self.prompts: list[str] = []

    async def generate_json(self, prompt: str, *, request_id: str) -> dict:
        self.prompts.append(prompt)
        if not self._responses:
            raise RuntimeError("StubGenerationProvider exhausted")
        return self._responses.pop(0)


class GeminiGeneration:
    name = "gemini"

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash",
                 timeout: float = 30.0) -> None:
        from google import genai
        self._client = genai.Client(api_key=api_key)
        self._model = model
        self._timeout = timeout

    async def generate_json(self, prompt: str, *, request_id: str) -> dict:
        resp = await self._client.aio.models.generate_content(
            model=self._model, contents=prompt,
            config={"response_mime_type": "application/json", "temperature": 0.2},
        )
        return json.loads(resp.text)


class GroqGeneration:
    name = "groq"

    def __init__(self, api_key: str, model: str = "llama-3.3-70b-versatile",
                 timeout: float = 30.0) -> None:
        from groq import AsyncGroq
        self._client = AsyncGroq(api_key=api_key, timeout=timeout)
        self._model = model

    async def generate_json(self, prompt: str, *, request_id: str) -> dict:
        resp = await self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        return json.loads(resp.choices[0].message.content)


class FallbackChain:
    """Primary -> one fallback -> ProviderUnavailable.

    Deliberately two providers, not three: each additional provider multiplies
    prompt-compatibility testing across differing structured-output support and
    error semantics (spec 3.2).
    """

    name = "chain"

    def __init__(self, primary: GenerationProvider,
                 fallback: GenerationProvider | None) -> None:
        self.primary = primary
        self.fallback = fallback

    async def generate_json(self, prompt: str, *, request_id: str) -> dict:
        try:
            return await self.primary.generate_json(prompt, request_id=request_id)
        except Exception as exc:  # noqa: BLE001 - any provider failure triggers fallback
            log_stage(request_id, "provider_failover",
                      provider=self.primary.name, error=str(exc)[:200])
            if self.fallback is None:
                raise ProviderUnavailable(f"{self.primary.name} failed: {exc}") from exc

        try:
            return await self.fallback.generate_json(prompt, request_id=request_id)
        except Exception as exc:  # noqa: BLE001
            raise ProviderUnavailable(
                f"both {self.primary.name} and {self.fallback.name} failed: {exc}") from exc
