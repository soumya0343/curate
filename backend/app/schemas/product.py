from typing import Any, Literal

from pydantic import BaseModel

TrustSource = Literal["title_verified", "inferred"]


class Attribute(BaseModel):
    """A product attribute with its provenance.

    `source` is what decides whether this attribute may exclude a product:
    "title_verified" may hard-filter, "inferred" may only rank, None means absent
    (docs/dataset.md 4.1).
    """
    value: Any = None
    source: TrustSource | None = None


class Product(BaseModel):
    id: str
    title: str
    title_original: str
    description: str = ""
    category: str
    price: float
    currency: str = "INR"
    price_tier: Literal["budget", "mid", "premium", "luxury"]
    rating: float
    reviews: int
    quality_score: float
    attributes: dict[str, Attribute] = {}
    image_url: str
    product_url: str

    def attr(self, name: str) -> Attribute | None:
        return self.attributes.get(name)

    def verified(self, name: str) -> Any | None:
        """Return the value only if it passed title verification, else None.

        Callers that hard-filter MUST use this rather than `attr`, so an inferred
        value can never exclude a product.
        """
        a = self.attributes.get(name)
        if a is None or a.source != "title_verified":
            return None
        return a.value
