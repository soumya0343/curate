"""Title normalisation shared by runtime ranking and offline ingest.

`variant_key` collapses colour/size variants of one product. It must be the same
function in both places: ingest uses it to keep one representative per variant
family, and rank-time diversity uses it as the second line of defence against
whatever survives ingest. Two divergent implementations would mean the runtime
penalises groupings the catalogue never formed.

Lives in `app/core/` rather than `scripts/` so the dependency runs runtime ->
nothing, and the offline pipeline imports inward.
"""
import re

# Amazon India titles are brand-first and keyword-dense: "<brand> <model> <type>
# <colour/size>". Five tokens reaches the product type on most listings while
# leaving the variant word outside the key, which is exactly what must be
# ignored. Six tokens keeps the colour word and stops collapsing anything.
VARIANT_TOKENS = 5


def normalise_title(title: str) -> str:
    return re.sub(r"\s+", " ", str(title).lower()).strip()


def variant_key(title: str) -> str:
    """Collapse colour/size variants of the same product to one key."""
    tokens = re.findall(r"[a-z0-9]+", normalise_title(title))
    return " ".join(tokens[:VARIANT_TOKENS])
