import json
from pathlib import Path

import numpy as np

from app.catalogue.loader import JsonlCatalogue
from app.config import Settings
from app.schemas.product import Product


class ManifestMismatch(RuntimeError):
    """Raised when configured embeddings differ from the built catalogue.

    Failing loudly here is the point: a silent mismatch would put query vectors in
    a different space from the catalogue, cosine would still return plausible
    numbers, and every result would be noise with nothing to debug against
    (spec 3.1).
    """


class CatalogueIndex:
    def __init__(self, products: list[Product], matrix: np.ndarray) -> None:
        if len(products) != matrix.shape[0]:
            raise ManifestMismatch(
                f"row misalignment: {len(products)} products, {matrix.shape[0]} vectors")
        self.products = products
        self.matrix = matrix.astype(np.float32)

    def search(self, query_vec: np.ndarray, subset: list[int] | None,
               top_k: int) -> list[tuple[int, float]]:
        """Return (row_index, similarity) pairs, best first.

        Vectors are L2-normalised at build time, so a dot product is the cosine.
        """
        if subset is not None:
            if not subset:
                return []
            rows = np.asarray(subset, dtype=np.int64)
            sims = self.matrix[rows] @ query_vec
        else:
            rows = np.arange(self.matrix.shape[0])
            sims = self.matrix @ query_vec

        k = min(top_k, sims.shape[0])
        top = np.argpartition(-sims, k - 1)[:k]
        top = top[np.argsort(-sims[top])]
        return [(int(rows[i]), float(sims[i])) for i in top]


def load_index(data_dir: Path, settings: Settings) -> CatalogueIndex:
    manifest = json.loads((data_dir / "embeddings.manifest.json").read_text())

    if manifest["model"] != settings.embedding_model:
        raise ManifestMismatch(
            f"catalogue built with {manifest['model']!r} but configured "
            f"embedding_model is {settings.embedding_model!r}. Rebuild embeddings.")
    if int(manifest["dims"]) != settings.embedding_dims:
        raise ManifestMismatch(
            f"catalogue built with {manifest['dims']} dims but configured "
            f"embedding_dims is {settings.embedding_dims}. Rebuild embeddings.")

    products = JsonlCatalogue(data_dir / "catalogue.jsonl.gz").load()
    matrix = np.load(data_dir / "embeddings.npy")
    return CatalogueIndex(products, matrix)
