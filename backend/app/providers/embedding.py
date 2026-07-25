"""Embedding providers.

There is deliberately NO fallback chain here. Query vectors must come from the
same model and dimensionality as the catalogue matrix; a dynamic swap would put
them in a different space, cosine would still return plausible numbers, and every
result would be noise with nothing to debug against (spec 3.1).

A missing embedding provider is a hard failure, which is correct: silently wrong
retrieval is worse than a clear error.
"""
import hashlib
from typing import Protocol

import numpy as np


class EmbeddingProvider(Protocol):
    model: str
    dims: int

    async def embed(self, texts: list[str]) -> np.ndarray: ...


class GeminiEmbedding:
    def __init__(self, api_key: str, model: str, dims: int) -> None:
        from google import genai
        self._client = genai.Client(api_key=api_key)
        self.model = model
        self.dims = dims

    async def embed(self, texts: list[str]) -> np.ndarray:
        resp = await self._client.aio.models.embed_content(
            model=self.model, contents=texts,
            config={"output_dimensionality": self.dims, "task_type": "RETRIEVAL_QUERY"},
        )
        matrix = np.asarray([e.values for e in resp.embeddings], dtype=np.float32)
        return matrix / np.linalg.norm(matrix, axis=1, keepdims=True)


class StubEmbedding:
    """Deterministic hash-based vectors for tests.

    Same text always yields the same vector; different texts yield different ones.
    That is all the pipeline tests need.
    """

    model = "stub"

    def __init__(self, dims: int = 768) -> None:
        self.dims = dims

    async def embed(self, texts: list[str]) -> np.ndarray:
        out = np.empty((len(texts), self.dims), dtype=np.float32)
        for i, text in enumerate(texts):
            seed = int.from_bytes(hashlib.sha256(text.encode()).digest()[:8], "big")
            out[i] = np.random.default_rng(seed).standard_normal(self.dims)
        return out / np.linalg.norm(out, axis=1, keepdims=True)
