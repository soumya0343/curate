from app.schemas.intent import Assumption, ShoppingIntent, SubNeed
from app.schemas.product import Attribute, Product


def _product(**overrides) -> Product:
    base = dict(
        id="B08XYZ", title="Wildcraft 45L Rucksack Water Resistant Trekking Backpack",
        title_original="Wildcraft 45L Rucksack Water Resistant Trekking Backpack",
        description="A 45-litre rucksack.", category="Backpacks",
        price=3499.0, price_tier="mid", rating=4.3, reviews=212, quality_score=23.1,
        attributes={
            "capacity_l": Attribute(value=45, source="title_verified"),
            "use_case": Attribute(value=["trekking"], source="inferred"),
            "material": Attribute(value=None, source=None),
        },
        image_url="https://m.media-amazon.com/x.jpg",
        product_url="https://www.amazon.in/dp/B08XYZ",
    )
    base.update(overrides)
    return Product(**base)


def test_verified_returns_value_only_for_title_verified():
    p = _product()
    assert p.verified("capacity_l") == 45
    assert p.verified("use_case") is None       # inferred never counts as verified
    assert p.verified("material") is None
    assert p.verified("missing_field") is None


def test_attr_returns_attribute_or_none():
    p = _product()
    assert p.attr("use_case").value == ["trekking"]
    assert p.attr("nope") is None


def test_intent_fields_all_optional():
    i = ShoppingIntent()
    assert i.budget_max is None and i.gender is None


def test_sub_need_requires_label_and_query():
    s = SubNeed(label="Backpack", query="50L trekking rucksack")
    assert s.label == "Backpack"


def test_assumption_defaults_to_editable():
    a = Assumption(field="climate", value="cold-weather likely",
                   reason="high-altitude trek in late October", confidence="medium")
    assert a.editable is True
