from functools import lru_cache

from app.catalogue.index import load_index
from app.config import Settings, get_settings
from app.core.errors import ProviderUnavailable
from app.providers.embedding import (EmbeddingProvider, GeminiEmbedding,
                                     HashingEmbedding, JinaEmbedding)
from app.providers.generation import (CerebrasGeneration, FallbackChain,
                                      GeminiGeneration, GenerationProvider,
                                      GitHubModelsGeneration, GroqGeneration,
                                      MockGeneration)
from app.schemas.product import Product
from app.services.pipeline import RecommendationPipeline
from app.services.sessions import SessionStore

_sessions: SessionStore | None = None


def _build_generation(settings: Settings) -> GenerationProvider:
    """Assemble the generation chain named by GENERATION_CHAIN (or the legacy
    primary + fallback pair).

    A provider with no key is skipped rather than raising: a chain of
    gemini,cerebras,groq should still start for someone who only holds two of
    the three. Only an empty chain is an error, and it names what is missing.
    """
    timeout = settings.llm_timeout_seconds
    builders = {
        "gemini": lambda keys: GeminiGeneration(keys, model=settings.gemini_model,
                                                timeout=timeout),
        "groq": lambda keys: GroqGeneration(keys, model=settings.groq_model,
                                            timeout=timeout),
        "cerebras": lambda keys: CerebrasGeneration(
            keys, model=settings.cerebras_model,
            base_url=settings.cerebras_base_url, timeout=timeout),
        "github": lambda keys: GitHubModelsGeneration(
            keys, model=settings.github_model,
            base_url=settings.github_base_url, timeout=timeout),
    }

    order = settings.generation_order()

    # mock is the keyless rule-based provider: keyword matching, not a model.
    # It ends any chain it appears in, since it never fails and never rate
    # limits - anything after it would be unreachable.
    providers: list[GenerationProvider] = []
    missing: list[str] = []
    for name in order:
        if name == "mock":
            providers.append(MockGeneration())
            break
        builder = builders.get(name)
        if builder is None:
            raise ProviderUnavailable(f"unknown generation provider {name!r}")
        keys = settings.keys_for(name)
        if keys:
            providers.append(builder(keys))
        else:
            missing.append(name)

    if not providers:
        raise ProviderUnavailable(
            f"no API key configured for any provider in the chain {order} "
            f"(missing keys: {', '.join(missing) or 'all'})")

    return FallbackChain(*providers)


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

    if settings.embedding_model == JinaEmbedding.model:
        keys = settings.keys_for("jina")
        if not keys:
            raise ProviderUnavailable("JINA_API_KEY is required for embeddings")
        # "retrieval.query": the catalogue matrix was built with the document
        # task ("retrieval.passage", JinaEmbedding's default); queries need the
        # asymmetric counterpart, not the same task type as the documents.
        return JinaEmbedding(keys, task="retrieval.query")

    keys = settings.keys_for("gemini")
    if not keys:
        raise ProviderUnavailable("GEMINI_API_KEY is required for embeddings")
    # Several keys rotate on a rate limit; the model never changes, so every
    # vector still lands in the catalogue's space.
    return GeminiEmbedding(keys, settings.embedding_model, settings.embedding_dims)


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


def get_products() -> list[Product]:
    """The same in-memory catalogue app/services/retrieval.py searches.

    Catalogue browsing and recommendation read one loaded list, not two
    stores kept in sync - see app/catalogue/browse.py.
    """
    return get_pipeline().index.products
