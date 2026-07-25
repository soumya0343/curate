from app.config import Settings


def test_defaults_pin_embedding_model():
    s = Settings(_env_file=None)
    assert s.embedding_model == "gemini-embedding-001"
    assert s.embedding_dims == 768


def test_cors_origins_parses_comma_separated(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5173,https://x.vercel.app")
    s = Settings()
    assert s.cors_origins == ["http://localhost:5173", "https://x.vercel.app"]
