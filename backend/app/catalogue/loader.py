import gzip
import json
from pathlib import Path
from typing import Protocol

from app.schemas.product import Product


class CatalogueSource(Protocol):
    def load(self) -> list[Product]: ...


class JsonlCatalogue:
    """Reads a gzipped JSONL catalogue.

    Line order is significant: it must match row order in embeddings.npy.
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> list[Product]:
        opener = gzip.open if self.path.suffix == ".gz" else open
        with opener(self.path, "rt", encoding="utf-8") as f:
            return [Product.model_validate(json.loads(line)) for line in f if line.strip()]
