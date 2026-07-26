"""Embedding providers.

There is deliberately NO fallback chain here. Query vectors must come from the
same model and dimensionality as the catalogue matrix; a dynamic swap would put
them in a different space, cosine would still return plausible numbers, and every
result would be noise with nothing to debug against (spec 3.1).

A missing embedding provider is a hard failure, which is correct: silently wrong
retrieval is worse than a clear error.
"""
import hashlib
import math
import re
from typing import Protocol

import numpy as np

from app.providers.keys import KeyRing, call_with_rotation


class EmbeddingProvider(Protocol):
    model: str
    dims: int

    async def embed(self, texts: list[str]) -> np.ndarray: ...


class GeminiEmbedding:
    """Gemini embeddings, with key rotation but never provider fallback.

    The distinction is the whole point: a second KEY is the same model producing
    vectors in the same space, so rotating is invisible to correctness. A second
    PROVIDER is a different space, where cosine still returns plausible numbers
    and every result is noise (spec 3.1). Rate limits are worth surviving;
    silently wrong retrieval is not.
    """

    def __init__(self, api_keys: str | list[str], model: str, dims: int) -> None:
        self._ring = KeyRing(api_keys)
        self.model = model
        self.dims = dims
        self._clients: dict[str, object] = {}

    def _client(self, api_key: str):
        if api_key not in self._clients:
            from google import genai
            self._clients[api_key] = genai.Client(api_key=api_key)
        return self._clients[api_key]

    async def embed(self, texts: list[str]) -> np.ndarray:
        async def call(api_key: str) -> np.ndarray:
            resp = await self._client(api_key).aio.models.embed_content(
                model=self.model, contents=texts,
                config={"output_dimensionality": self.dims,
                        "task_type": "RETRIEVAL_QUERY"},
            )
            matrix = np.asarray([e.values for e in resp.embeddings], dtype=np.float32)
            return matrix / np.linalg.norm(matrix, axis=1, keepdims=True)

        return await call_with_rotation(self._ring, call, request_id="embed",
                                        provider="gemini-embedding")


class HashingEmbedding:
    """Keyless lexical embeddings: hashed bag of words, L2-normalised.

    Exists so the application can run end to end with no API key - local
    development, the synthetic catalogue in `data/mock/`, and any environment
    where a network call to Gemini is not available. Unlike `StubEmbedding`,
    which returns seeded noise, this carries real lexical signal: "trekking
    rucksack" scores against "Trekking Backpack" because they share a token.

    It is emphatically NOT a semantic model. Synonyms miss ("rucksack" vs
    "backpack" share nothing), word order is discarded, and nothing generalises
    beyond surface overlap. It stands in for retrieval; it does not imitate it.

    The same instance builds the catalogue matrix and encodes queries, which is
    what keeps both in one vector space - the property `embeddings.manifest.json`
    pins and `load_index` enforces.
    """

    model = "hashing-bow-v1"

    # Query-shaped filler that would otherwise dominate the overlap: every
    # product would match "for" and "with" equally, which is noise, not signal.
    _STOPWORDS = frozenset("""
        a an the and or of for with to in on at by from is are be this that my me
        i we you it as under below within over about need needs want looking find
        get good best some any please rs inr rupees""".split())

    _TOKEN = re.compile(r"[a-z0-9]+")

    def __init__(self, dims: int = 256) -> None:
        self.dims = dims

    def _bucket(self, token: str) -> int:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        return int.from_bytes(digest, "big") % self.dims

    def encode(self, texts: list[str]) -> np.ndarray:
        """Synchronous encoder, used offline when building a catalogue matrix."""
        out = np.zeros((len(texts), self.dims), dtype=np.float32)
        for i, text in enumerate(texts):
            counts: dict[int, float] = {}
            for token in self._TOKEN.findall(str(text).lower()):
                if token in self._STOPWORDS or len(token) < 2:
                    continue
                bucket = self._bucket(token)
                counts[bucket] = counts.get(bucket, 0.0) + 1.0
            for bucket, count in counts.items():
                # Sublinear term frequency: a title repeating "shoes" four times
                # is not four times as much about shoes.
                out[i, bucket] = 1.0 + math.log(count)

        norms = np.linalg.norm(out, axis=1, keepdims=True)
        # A text of nothing but stopwords produces a zero row; leave it at zero
        # rather than dividing by zero. It simply matches nothing.
        np.divide(out, norms, out=out, where=norms > 0)
        return out

    async def embed(self, texts: list[str]) -> np.ndarray:
        return self.encode(texts)


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
