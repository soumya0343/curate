"""Tier-B verifiers: confirm an extracted attribute against the source title.

Governing rule (docs/dataset.md 4.1): tier B may participate in hard filters
ONLY after passing verification here. A value that fails is demoted to tier C,
where it can rank but never exclude.

Verifiers run against the ORIGINAL title, never a translation — a translation
artifact must not be able to manufacture a verified fact.
"""
import re

TIER_B_FIELDS = frozenset({"capacity_l", "water_resistant", "gender", "material",
                           "brand", "pack_count"})

_GENDER_PATTERNS = {
    "men": r"\b(men|men's|mens|male|boys)\b",
    "women": r"\b(women|women's|womens|female|girls|ladies)\b",
    "unisex": r"\bunisex\b",
}


def _verify_capacity(value, title: str) -> bool:
    if not isinstance(value, (int, float)):
        return False
    n = int(value)
    return bool(re.search(rf"\b{n}\s*(l|ltr|litre|liter|liters|litres)\b", title, re.I))


def _verify_water_resistant(value, title: str) -> bool:
    if value is False:
        return True  # negative claims exclude nothing
    return bool(re.search(r"water[\s\-]?(resistant|proof)|waterproof", title, re.I))


def _verify_gender(value, title: str) -> bool:
    pattern = _GENDER_PATTERNS.get(str(value).lower())
    return bool(pattern and re.search(pattern, title, re.I))


def _verify_material(value, title: str) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    return bool(re.search(rf"\b{re.escape(value)}\b", title, re.I))


def _verify_brand(value, title: str) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    return bool(re.search(rf"\b{re.escape(value)}\b", title, re.I))


def _verify_pack_count(value, title: str) -> bool:
    if not isinstance(value, (int, float)):
        return False
    n = int(value)
    return bool(re.search(rf"\b(pack of|set of|pcs of)\s*{n}\b|\b{n}\s*(pcs|pieces|pack)\b",
                          title, re.I))


_VERIFIERS = {
    "capacity_l": _verify_capacity,
    "water_resistant": _verify_water_resistant,
    "gender": _verify_gender,
    "material": _verify_material,
    "brand": _verify_brand,
    "pack_count": _verify_pack_count,
}


def verify(field: str, value, source_title: str) -> bool:
    """True if `value` for `field` is supported by `source_title`.

    Unknown fields always return False: a field with no verifier cannot be tier B.
    """
    fn = _VERIFIERS.get(field)
    if fn is None or value is None:
        return False
    return fn(value, source_title or "")
