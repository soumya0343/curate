from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    gemini_api_key: str | None = None
    groq_api_key: str | None = None
    cerebras_api_key: str | None = None

    # Plural forms hold several keys for one provider, comma-separated. Free
    # tiers are what this project actually runs out of, so a rate limit rotates
    # to the next key rather than failing the request. Singular and plural are
    # merged by keys_for(); either spelling works.
    gemini_api_keys: Annotated[list[str], NoDecode] = []
    groq_api_keys: Annotated[list[str], NoDecode] = []
    cerebras_api_keys: Annotated[list[str], NoDecode] = []

    # GitHub Models authenticates with a personal access token carrying the
    # models:read scope, so it is a token rather than an API key. keys_for()
    # accepts both spellings.
    github_token: str | None = None
    github_tokens: Annotated[list[str], NoDecode] = []

    generation_primary: str = "gemini"
    generation_fallback: str | None = "groq"
    # Ordered chain, comma-separated: GENERATION_CHAIN=gemini,cerebras,groq.
    # Overrides primary/fallback when set.
    generation_chain: Annotated[list[str], NoDecode] = []

    # Model ids drift, and a retired one fails at the first real request while
    # every offline test still passes. Two of these broke within a day of being
    # written, so all four are settings rather than constructor defaults.
    # `-latest` aliases are preferred where a provider offers them.
    gemini_model: str = "gemini-flash-latest"
    groq_model: str = "llama-3.3-70b-versatile"

    cerebras_model: str = "gpt-oss-120b"
    cerebras_base_url: str = "https://api.cerebras.ai/v1"

    github_model: str = "openai/gpt-4o-mini"
    github_base_url: str = "https://models.github.ai/inference"

    # Pinned. Changing either requires rebuilding catalogue embeddings.
    embedding_model: str = "gemini-embedding-001"
    embedding_dims: int = 768

    data_dir: Path = Path(__file__).parent.parent / "data"

    # NoDecode stops pydantic-settings JSON-decoding this env var before our
    # validator runs — without it, a comma-separated CORS_ORIGINS raises
    # SettingsError instead of reaching _split_origins.
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]

    session_ttl_seconds: int = 1800
    llm_timeout_seconds: float = 30.0
    database_url: str = "postgresql://postgres:postgres@localhost:5432/catalogue"

    @field_validator("cors_origins", "gemini_api_keys", "groq_api_keys",
                     "cerebras_api_keys", "github_tokens", "generation_chain",
                     mode="before")
    @classmethod
    def _split_csv(cls, v):
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v

    # GitHub Models uses a PAT, so its settings are *_token(s) rather than
    # *_api_key(s). Everything else follows the api_key convention.
    _CREDENTIAL_SUFFIX = {"github": ("token", "tokens")}

    def keys_for(self, provider: str) -> list[str]:
        """Every credential configured for a provider, singular and plural merged.

        Order is preserved and duplicates are dropped downstream by KeyRing,
        so setting GEMINI_API_KEY and GEMINI_API_KEYS with an overlap is safe.
        """
        single_suffix, plural_suffix = self._CREDENTIAL_SUFFIX.get(
            provider, ("api_key", "api_keys"))
        single = getattr(self, f"{provider}_{single_suffix}", None)
        plural = getattr(self, f"{provider}_{plural_suffix}", []) or []
        return [k for k in ([single] if single else []) + list(plural) if k]

    def generation_order(self) -> list[str]:
        """The provider chain, longest-form setting winning.

        GENERATION_CHAIN is the explicit form. Falling back to
        primary + fallback keeps every existing deployment and .env working
        unchanged.
        """
        if self.generation_chain:
            return list(self.generation_chain)
        order = [self.generation_primary]
        if self.generation_fallback and self.generation_fallback != self.generation_primary:
            order.append(self.generation_fallback)
        return order


@lru_cache
def get_settings() -> Settings:
    return Settings()
