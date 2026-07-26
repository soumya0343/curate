from functools import lru_cache

from app.catalogue.index import load_index
from app.config import Settings, get_settings
from app.core.errors import ProviderUnavailable
from app.providers.embedding import GeminiEmbedding
from app.providers.generation import (FallbackChain, GeminiGeneration,
                                      GenerationProvider, GroqGeneration)
from app.services.pipeline import RecommendationPipeline
from app.services.sessions import SessionStore

_sessions: SessionStore | None = None


def _build_generation(settings: Settings) -> GenerationProvider:
    builders = {
        "gemini": lambda: GeminiGeneration(settings.gemini_api_key,
                                           timeout=settings.llm_timeout_seconds),
        "groq": lambda: GroqGeneration(settings.groq_api_key,
                                       timeout=settings.llm_timeout_seconds),
    }
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


@lru_cache
def get_pipeline() -> RecommendationPipeline:
    global _sessions
    settings = get_settings()
    if _sessions is None:
        _sessions = SessionStore(ttl_seconds=settings.session_ttl_seconds)

    # No embedding fallback by design: query vectors must share the catalogue's
    # vector space, and the manifest check enforces it (spec 3.1).
    if not settings.gemini_api_key:
        raise ProviderUnavailable("GEMINI_API_KEY is required for embeddings")

    return RecommendationPipeline(
        index=load_index(settings.data_dir, settings),
        embedder=GeminiEmbedding(settings.gemini_api_key,
                                 settings.embedding_model, settings.embedding_dims),
        generator=_build_generation(settings),
        sessions=_sessions,
    )
