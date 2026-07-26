from functools import lru_cache

from app.catalogue.index import load_index
from app.config import Settings, get_settings
from app.core.errors import ProviderUnavailable
from app.providers.embedding import (EmbeddingProvider, GeminiEmbedding,
                                     HashingEmbedding)
from app.providers.generation import (FallbackChain, GeminiGeneration,
                                      GenerationProvider, GroqGeneration,
                                      MockGeneration)
from app.services.pipeline import RecommendationPipeline
from app.services.sessions import SessionStore

_sessions: SessionStore | None = None


def _build_generation(settings: Settings) -> GenerationProvider:
    builders = {
        "gemini": lambda: GeminiGeneration(settings.gemini_api_key,
                                           timeout=settings.llm_timeout_seconds),
        "groq": lambda: GroqGeneration(settings.groq_api_key,
                                       timeout=settings.llm_timeout_seconds),
        "mock": MockGeneration,
    }
    # GENERATION_PRIMARY=mock runs the rule-based provider, which needs no key.
    # It exists for demos and local development against the synthetic catalogue;
    # it matches keywords rather than reading a request.
    if settings.generation_primary == "mock":
        return MockGeneration()

    keys = {"gemini": settings.gemini_api_key, "groq": settings.groq_api_key}

    if not keys.get(settings.generation_primary):
        raise ProviderUnavailable(
            f"no API key configured for primary provider {settings.generation_primary!r}")

    primary = builders[settings.generation_primary]()
    fallback = None
    name = settings.generation_fallback
    if name and name != settings.generation_primary and keys.get(name):
        fallback = builders[name]()
    return FallbackChain(primary, fallback)


def _build_embedding(settings: Settings) -> EmbeddingProvider:
    """Pick the embedder named by EMBEDDING_MODEL. There is no fallback.

    Query vectors must share the catalogue's vector space; `load_index` refuses
    to start unless this same model name and dimensionality appear in
    `embeddings.manifest.json`, so choosing here and pinning there are the two
    halves of one check (spec 3.1).
    """
    if settings.embedding_model == HashingEmbedding.model:
        # Keyless lexical embeddings, for the synthetic catalogue and local runs.
        return HashingEmbedding(dims=settings.embedding_dims)

    if not settings.gemini_api_key:
        raise ProviderUnavailable("GEMINI_API_KEY is required for embeddings")
    return GeminiEmbedding(settings.gemini_api_key, settings.embedding_model,
                           settings.embedding_dims)


@lru_cache
def get_pipeline() -> RecommendationPipeline:
    global _sessions
    settings = get_settings()
    if _sessions is None:
        _sessions = SessionStore(ttl_seconds=settings.session_ttl_seconds)

    return RecommendationPipeline(
        index=load_index(settings.data_dir, settings),
        embedder=_build_embedding(settings),
        generator=_build_generation(settings),
        sessions=_sessions,
    )
