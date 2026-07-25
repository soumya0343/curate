from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    gemini_api_key: str | None = None
    groq_api_key: str | None = None

    generation_primary: str = "gemini"
    generation_fallback: str | None = "groq"

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

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v):
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
