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

from app.core.errors import RateLimited
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


class JinaEmbedding:
    """Jina AI embeddings via plain httpx, no vendor SDK - same rationale as
    `OpenAICompatibleGeneration` (app/providers/generation.py): one less SDK is
    one less place for a client-construction difference to hide.

    Free tier is 100 RPM / 100K TPM (vs. e.g. Cohere's 1,000 calls/month trial),
    comfortably enough headroom for a one-off catalogue embed of a few thousand
    products.

    `jina-embeddings-v3` supports Matryoshka truncation via `dimensions`, so
    `dims=768` matches this project's existing `EMBEDDING_DIMS` default rather
    than forcing a config change when swapping providers.

    `task` matters here in a way it did not for `GeminiEmbedding`'s single
    `RETRIEVAL_QUERY` simplification: Jina's `retrieval.passage` /
    `retrieval.query` activate different LoRA adapters, and using the document
    task for query text measurably hurt retrieval in testing (a bluetooth-
    adapter listing outranked actual headphones for "wireless bluetooth
    headphones"). So the two are kept genuinely separate: the offline catalogue
    builder (`scripts/catalogue_build.py`) constructs this with the default
    `retrieval.passage`, and `app/api/deps.py` constructs a second instance with
    `task="retrieval.query"` for runtime query embedding. The catalogue matrix
    and the query vector still share one model and dimensionality - just the
    asymmetric task-specific encoding, which is what Jina's adapters exist for.

    A documented RPM ceiling is a ceiling, not a guarantee against a burst
    limit underneath it: firing every chunk back-to-back with no spacing hit a
    429 well before the free tier's stated 100 RPM. `_PACE_SECONDS` spaces
    chunks out; `_MAX_RETRIES` retries a still-rate-limited or transiently
    disconnected call with backoff rather than failing a whole catalogue build
    over one transient error - safe here because this method is also used for
    single-chunk live query embedding, where a short bounded retry is a
    reasonable answer to a rate limit, not a user-facing stall.
    """

    model = "jina-embeddings-v3"
    dims = 768
    _MAX_BATCH = 100
    _PACE_SECONDS = 2.0
    _MAX_RETRIES = 5

    def __init__(self, api_keys: str | list[str], task: str = "retrieval.passage",
                 timeout: float = 30.0) -> None:
        self._ring = KeyRing(api_keys)
        self._task = task
        self._timeout = timeout

    async def embed(self, texts: list[str]) -> np.ndarray:
        import asyncio

        import httpx

        async def call_chunk(chunk: list[str]) -> np.ndarray:
            async def call(api_key: str) -> np.ndarray:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.post(
                        "https://api.jina.ai/v1/embeddings",
                        headers={"Authorization": f"Bearer {api_key}",
                                 "Content-Type": "application/json"},
                        json={"model": self.model, "input": chunk,
                              "task": self._task, "dimensions": self.dims},
                    )
                    resp.raise_for_status()
                    payload = resp.json()
                ordered = sorted(payload["data"], key=lambda d: d["index"])
                vectors = np.asarray([d["embedding"] for d in ordered], dtype=np.float32)
                return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)

            for attempt in range(self._MAX_RETRIES):
                try:
                    return await call_with_rotation(self._ring, call, request_id="embed",
                                                    provider="jina-embedding")
                except (RateLimited, httpx.TransportError):
                    # RateLimited is a real 429; TransportError is a connection
                    # blip (DNS hiccup, dropped connection) - transient either
                    # way over a sequential run of dozens of calls, and not a
                    # reason to lose all prior progress in this run.
                    if attempt == self._MAX_RETRIES - 1:
                        raise
                    await asyncio.sleep(2 ** attempt)  # 1s, 2s, 4s, 8s

        chunks = [texts[i:i + self._MAX_BATCH] for i in range(0, len(texts), self._MAX_BATCH)]
        results = []
        for i, chunk in enumerate(chunks):
            if i:
                await asyncio.sleep(self._PACE_SECONDS)
            results.append(await call_chunk(chunk))
        return np.vstack(results)


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
