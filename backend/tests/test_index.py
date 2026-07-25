import gzip
import json

import numpy as np
import pytest

from app.catalogue.index import CatalogueIndex, ManifestMismatch, load_index
from app.catalogue.loader import JsonlCatalogue


def _row(i: int) -> dict:
    return {
        "id": f"B{i}", "title": f"Product {i}", "title_original": f"Product {i}",
        "description": "", "category": "Test", "price": 100.0 + i, "price_tier": "mid",
        "rating": 4.0, "reviews": 10, "quality_score": 9.6, "attributes": {},
        "image_url": "https://x/i.jpg", "product_url": f"https://www.amazon.in/dp/B{i}",
    }


@pytest.fixture
def data_dir(tmp_path):
    with gzip.open(tmp_path / "catalogue.jsonl.gz", "wt", encoding="utf-8") as f:
        for i in range(3):
            f.write(json.dumps(_row(i)) + "\n")
    m = np.eye(3, 4, dtype=np.float16)          # 3 orthogonal unit vectors
    np.save(tmp_path / "embeddings.npy", m)
    (tmp_path / "embeddings.manifest.json").write_text(json.dumps(
        {"model": "gemini-embedding-001", "dims": 4, "count": 3, "normalised": True}))
    return tmp_path


def test_loader_reads_gzipped_jsonl(data_dir):
    products = JsonlCatalogue(data_dir / "catalogue.jsonl.gz").load()
    assert [p.id for p in products] == ["B0", "B1", "B2"]


def test_search_ranks_by_cosine(data_dir):
    products = JsonlCatalogue(data_dir / "catalogue.jsonl.gz").load()
    idx = CatalogueIndex(products, np.load(data_dir / "embeddings.npy"))
    hits = idx.search(np.array([0, 1, 0, 0], dtype=np.float32), None, top_k=2)
    assert hits[0][0] == 1
    assert hits[0][1] == pytest.approx(1.0, abs=1e-3)


def test_search_respects_subset(data_dir):
    products = JsonlCatalogue(data_dir / "catalogue.jsonl.gz").load()
    idx = CatalogueIndex(products, np.load(data_dir / "embeddings.npy"))
    hits = idx.search(np.array([0, 1, 0, 0], dtype=np.float32), subset=[0, 2], top_k=2)
    assert {h[0] for h in hits} == {0, 2}


def test_search_on_empty_subset_returns_nothing(data_dir):
    products = JsonlCatalogue(data_dir / "catalogue.jsonl.gz").load()
    idx = CatalogueIndex(products, np.load(data_dir / "embeddings.npy"))
    assert idx.search(np.array([1, 0, 0, 0], dtype=np.float32), subset=[], top_k=5) == []


def test_load_index_rejects_model_mismatch(data_dir):
    from app.config import Settings
    s = Settings(_env_file=None, embedding_model="some-other-model", embedding_dims=4)
    with pytest.raises(ManifestMismatch, match="some-other-model"):
        load_index(data_dir, s)


def test_load_index_rejects_dims_mismatch(data_dir):
    from app.config import Settings
    s = Settings(_env_file=None, embedding_model="gemini-embedding-001", embedding_dims=768)
    with pytest.raises(ManifestMismatch, match="768"):
        load_index(data_dir, s)
