"""Shared catalogue-artifact writer.

Both `build_mock_catalogue.py` (synthetic fixture) and `ingest_enriched.py` (the
real Kaggle-derived catalogue) produce the same three files —
`catalogue.jsonl.gz`, `embeddings.npy`, `embeddings.manifest.json` — and must
honour the same contract: JSONL line order equals embedding matrix row order
(`app/catalogue/index.py` refuses to start otherwise). This module is the one
place that contract is implemented, so neither builder can drift from it.
"""
import gzip
import json
from datetime import date
from pathlib import Path

import numpy as np

from scripts.verify_attributes import verify

GEMINI_MODEL = "gemini-embedding-001"
GEMINI_DIMS = 768


def apply_trust_tiers(attrs: dict, source_title: str, tier_b_fields: frozenset) -> dict:
    """Attach provenance, verifying tier-B claims against the source title.

    Deliberately uses the production verifiers rather than trusting whatever
    produced `attrs` - a catalogue built by bypassing the tier rule would hide
    exactly the bug the tier rule exists to catch (docs/dataset.md 4.1).
    """
    out: dict[str, dict] = {}
    for field, value in attrs.items():
        if value is None or value == []:
            out[field] = {"value": None, "source": None}
        elif field in tier_b_fields and verify(field, value, source_title):
            out[field] = {"value": value, "source": "title_verified"}
        else:
            out[field] = {"value": value, "source": "inferred"}
    return out


def searchable_text(product: dict) -> str:
    """Flatten a product into the text that gets embedded."""
    parts = [product["title"], product["description"], product["category"]]
    for attr in product["attributes"].values():
        value = attr["value"]
        if value is None or value == [] or isinstance(value, bool):
            continue
        if isinstance(value, list):
            parts.extend(str(v) for v in value)
        else:
            parts.append(str(value))
    return " | ".join(p for p in parts if p)


def _gemini_matrix(texts: list[str], model: str, dims: int) -> np.ndarray:
    """Embed with the real provider, when a key is available.

    Worth the API call: the hashing embedder has no IDF, so a title sharing
    "cotton" or "women" scores as highly as one sharing "thermal", and searching
    "thermal base layer" surfaces sarees. Real embeddings remove the one part of
    a keyless stack that misrepresents how retrieval behaves.
    """
    import asyncio

    from app.config import get_settings
    from app.providers.embedding import GeminiEmbedding

    keys = get_settings().keys_for("gemini")
    if not keys:
        raise SystemExit("--embedder gemini needs GEMINI_API_KEY")

    embedder = GeminiEmbedding(keys, model, dims)

    async def run() -> np.ndarray:
        # Batched: one request per 100 texts, well inside the payload limit.
        chunks = [texts[i:i + 100] for i in range(0, len(texts), 100)]
        return np.vstack([await embedder.embed(chunk) for chunk in chunks])

    return asyncio.run(run())


def _jina_matrix(texts: list[str]) -> np.ndarray:
    """Embed with Jina AI, when a key is available.

    Free tier (100 RPM / 100K TPM) has enough headroom for a one-off catalogue
    build where Gemini's much tighter embedding quota does not.
    """
    import asyncio

    from app.config import get_settings
    from app.providers.embedding import JinaEmbedding

    keys = get_settings().keys_for("jina")
    if not keys:
        raise SystemExit("--embedder jina needs JINA_API_KEY")

    return asyncio.run(JinaEmbedding(keys).embed(texts))


def embed_matrix(texts: list[str], embedder: str, dims: int) -> tuple[np.ndarray, str, int]:
    """Return (matrix, model_id, dims actually used) for the chosen embedder."""
    if embedder == "gemini":
        model, dims = GEMINI_MODEL, GEMINI_DIMS
        matrix = _gemini_matrix(texts, model, dims)
    elif embedder == "jina":
        from app.providers.embedding import JinaEmbedding
        model, dims = JinaEmbedding.model, JinaEmbedding.dims
        matrix = _jina_matrix(texts)
    else:
        from app.providers.embedding import HashingEmbedding
        model = HashingEmbedding.model
        matrix = HashingEmbedding(dims=dims).encode(texts)
    return matrix, model, dims


def write(products: list[dict], out_dir: Path, *, dims: int, embedder: str,
          synthetic: bool, note: str) -> None:
    """Write catalogue.jsonl.gz + embeddings.npy + embeddings.manifest.json.

    Line order in the JSONL is row order in the matrix - the one invariant
    every caller must preserve upstream of this function.
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    with gzip.open(out_dir / "catalogue.jsonl.gz", "wt", encoding="utf-8") as f:
        for p in products:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")

    texts = [searchable_text(p) for p in products]
    matrix, model, dims = embed_matrix(texts, embedder, dims)
    np.save(out_dir / "embeddings.npy", matrix.astype(np.float16))

    (out_dir / "embeddings.manifest.json").write_text(json.dumps({
        "model": model,
        "dims": dims,
        "count": len(products),
        "normalised": True,
        "dtype": "float16",
        "built": date.today().isoformat(),
        "synthetic": synthetic,
        "note": note,
    }, indent=2))
