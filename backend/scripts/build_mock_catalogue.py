"""Build a small synthetic catalogue in the real catalogue format.

WHY THIS EXISTS. The real pipeline (ingest -> enrich -> embed) needs the 670 MB
source CSV and two API keys, and it is being built in parallel. Nothing
downstream of it - the API, the frontend, streaming, deployment - can be run or
demonstrated until it lands. This script produces artifacts with the same
filenames, the same schema, and the same manifest contract as the real pipeline,
so every one of those things can be exercised today.

WHAT IT IS NOT. The products are invented. The ASINs are fabricated, so
`product_url` resolves to nothing; the images are placeholders. No conclusion
about retrieval quality, catalogue coverage, or ranking may be drawn from it.
It exists to prove the machinery runs, not that the recommendations are good.

Written to `data/mock/`, never to `data/`, so a real catalogue can never be
silently shadowed by this one:

    data/mock/catalogue.jsonl.gz
    data/mock/embeddings.npy               float16, L2-normalised
    data/mock/embeddings.manifest.json     pins model + dims

Run:
    cd backend && python scripts/build_mock_catalogue.py
    DATA_DIR=data/mock EMBEDDING_MODEL=hashing-bow-v1 EMBEDDING_DIMS=256 \
      GENERATION_PRIMARY=mock uvicorn app.main:app --workers 1
"""
import bisect
import collections
import gzip
import json
import re
import sys
from datetime import date
from pathlib import Path

import numpy as np

# `python scripts/build_mock_catalogue.py` puts scripts/ on sys.path, not the
# backend root, so `app` and `scripts` are both unimportable without this.
# pytest gets it from pytest.ini's `pythonpath = .`; a direct run does not.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.providers.embedding import HashingEmbedding  # noqa: E402
from scripts.verify_attributes import TIER_B_FIELDS, verify  # noqa: E402

DIMS = 256
GEMINI_MODEL = "gemini-embedding-001"
GEMINI_DIMS = 768
OUT_DIR = Path("data/mock")
IMAGE_PLACEHOLDER = "https://placehold.co/400x400/eeeeee/555555?text="

# (category, title, price INR, stars, reviews)
SEEDS: list[tuple[str, str, float, float, int]] = [
    # --- Rucksacks & Trekking Backpacks
    ("Rucksacks & Trekking Backpacks", "Wildcraft 45L Rucksack Water Resistant Trekking Backpack for Men", 3499, 4.3, 2871),
    ("Rucksacks & Trekking Backpacks", "Decathlon Quechua MH100 30L Hiking Backpack Grey", 1799, 4.1, 940),
    ("Rucksacks & Trekking Backpacks", "Tripole Walker 55L Internal Frame Rucksack with Rain Cover", 4299, 4.4, 512),
    ("Rucksacks & Trekking Backpacks", "Impulse 60L Travel Rucksack Trekking Backpack Water Resistant", 2199, 3.9, 1804),
    ("Rucksacks & Trekking Backpacks", "Gokyo Kalindi 20L Daypack Hiking Backpack Lightweight", 1099, 4.0, 233),
    ("Rucksacks & Trekking Backpacks", "Adventure Worx Chimera 35L Trekking Backpack Nylon Blue", 2649, 4.2, 671),
    # --- Sports & Outdoor Shoes
    ("Sports & Outdoor Shoes", "Wildcraft Drifter Trekking Shoes for Men Water Resistant", 2999, 4.1, 1203),
    ("Sports & Outdoor Shoes", "Puma Softride Running Shoes for Men Grey", 3499, 4.3, 5412),
    ("Sports & Outdoor Shoes", "Campus Maxico Walking Shoes for Men Lightweight", 1299, 4.0, 8930),
    ("Sports & Outdoor Shoes", "Skechers Go Walk 6 Comfortable Walking Shoes for Women", 4499, 4.5, 2210),
    ("Sports & Outdoor Shoes", "Quechua NH100 Hiking Shoes Unisex Waterproof", 2199, 4.0, 388),
    ("Sports & Outdoor Shoes", "Bata Comfit Daily Walking Shoes for Women Black", 1599, 3.8, 1442),
    # --- Winterwear
    ("Men's Winterwear", "Wildcraft Polar Fleece Jacket for Men Full Sleeve Winter Wear", 1999, 4.2, 1780),
    ("Men's Winterwear", "Decathlon Forclaz MT100 Padded Winter Jacket for Men", 3999, 4.4, 620),
    ("Men's Winterwear", "Jockey Thermal Vest for Men Cotton Winter Innerwear", 799, 4.1, 3401),
    ("Men's Winterwear", "Woodland Water Resistant Windcheater Jacket for Men Olive", 4599, 4.0, 512),
    ("Women's Winterwear", "Monte Carlo Woollen Cardigan for Women Winter Wear", 2299, 4.2, 890),
    ("Women's Winterwear", "Decathlon Quechua Fleece Jacket for Women Warm Trekking Layer", 1599, 4.3, 1120),
    ("Women's Winterwear", "Jockey Thermal Leggings for Women Cotton Winter Base Layer", 949, 4.0, 2210),
    # --- Camping & Hiking
    ("Camping & Hiking", "Wildcraft Hypacool 1L Water Bottle Insulated Stainless Steel", 899, 4.2, 1533),
    ("Camping & Hiking", "Nite Ize Rechargeable LED Headlamp Water Resistant 300 Lumens", 1499, 4.1, 402),
    ("Camping & Hiking", "Quechua MH500 Trekking Poles Pair Aluminium Adjustable", 2499, 4.3, 188),
    ("Camping & Hiking", "Coleman Sleeping Bag Lightweight Camping Polyester", 3299, 4.0, 96),
    ("Camping & Hiking", "Wildcraft 20L Dry Bag Waterproof Rafting Sack", 1199, 4.1, 274),
    ("Camping & Hiking", "Amazon Basics Camping Lantern LED Battery Operated", 649, 3.9, 1866),
    # --- Women's Ethnic Wear
    ("Women's Ethnic Wear", "Libas Anarkali Kurta for Women Cotton Printed Festive Wear", 1499, 4.1, 6721),
    ("Women's Ethnic Wear", "Biba Silk Blend Saree for Women Wedding Wear with Blouse Piece", 4999, 4.3, 1240),
    ("Women's Ethnic Wear", "W for Woman Straight Kurta Set for Women Rayon Ethnic Wear", 2199, 4.0, 3390),
    ("Women's Ethnic Wear", "Kalini Banarasi Silk Lehenga Choli for Women Wedding", 8999, 4.2, 411),
    ("Women's Ethnic Wear", "Janasya Georgette Palazzo Kurta Set for Women Party Wear", 1799, 3.9, 2801),
    ("Women's Ethnic Wear", "Vishudh Cotton Kurti for Women Daily Ethnic Wear Blue", 799, 3.8, 5120),
    # --- Men's Ethnic Wear
    ("Men's Ethnic Wear", "Manyavar Silk Blend Kurta Pyjama Set for Men Wedding Wear", 3999, 4.3, 1902),
    ("Men's Ethnic Wear", "Peter England Cotton Kurta for Men Festive Ethnic Wear", 1299, 4.0, 2440),
    ("Men's Ethnic Wear", "Manyavar Embroidered Sherwani for Men Wedding Ceremony", 12999, 4.4, 322),
    ("Men's Ethnic Wear", "Aditya Nehru Jacket for Men Wedding Ethnic Layer Maroon", 2499, 4.1, 610),
    ("Men's Ethnic Wear", "Ramraj Cotton Dhoti for Men Traditional Wear White", 699, 3.9, 1180),
    # --- Gift Hampers
    ("Gift Hampers", "Ferrero Rocher Premium Chocolate Gift Hamper 24 Pieces", 1299, 4.5, 9820),
    ("Gift Hampers", "Nestasia Ceramic Tea Set Gift Hamper for Anniversary 6 Pieces", 3499, 4.2, 470),
    ("Gift Hampers", "Forest Essentials Luxury Skincare Gift Box for Women", 5999, 4.4, 388),
    ("Gift Hampers", "Titan Analog Watch Gift Set for Men Leather Strap", 7999, 4.3, 1560),
    ("Gift Hampers", "Bombay Shaving Company Premium Grooming Gift Kit for Men", 2199, 4.0, 2740),
    ("Gift Hampers", "Chumbak Premium Home Decor Gift Hamper Anniversary Set", 4499, 3.9, 210),
    ("Gift Hampers", "Rage Coffee Gourmet Gift Hamper Assorted Flavours", 1799, 4.1, 903),
    # --- Headphones & Earphones
    ("Headphones & Earphones", "boAt Rockerz 450 Bluetooth On Ear Headphones with Mic Black", 1499, 4.1, 128400),
    ("Headphones & Earphones", "boAt Rockerz 450 Bluetooth On Ear Headphones with Mic Blue", 1499, 4.0, 98210),
    ("Headphones & Earphones", "Sony WH CH520 Wireless Bluetooth Headphones with Mic", 4490, 4.4, 12030),
    ("Headphones & Earphones", "JBL Tune 510BT Wireless On Ear Headphones Pure Bass", 3499, 4.3, 22110),
    ("Headphones & Earphones", "Jabra Evolve2 30 Wired Office Headset with Noise Cancelling Mic", 8999, 4.2, 480),
    ("Headphones & Earphones", "OnePlus Bullets Wireless Z2 Bluetooth Earphones with Mic", 1999, 4.2, 41220),
    ("Headphones & Earphones", "Sennheiser HD 400S Wired Over Ear Headphones for Calls", 4999, 4.3, 1580),
    # --- Fitness Equipment
    ("Fitness Equipment", "Amazon Basics Neoprene Dumbbell Set 5 kg Pair for Home Workout", 1299, 4.2, 8410),
    ("Fitness Equipment", "Boldfit Yoga Mat 6mm Anti Skid for Home Workout Exercise", 899, 4.1, 32100),
    ("Fitness Equipment", "Kore Resistance Band Set for Beginners Home Workout", 599, 4.0, 14200),
    ("Fitness Equipment", "Cockatoo Adjustable Skipping Rope for Fitness Training", 349, 3.9, 6720),
    ("Fitness Equipment", "Aurion Push Up Bar Stand for Home Workout Steel", 799, 4.0, 2210),
    ("Fitness Equipment", "Strauss Foam Roller for Muscle Recovery and Stretching", 1099, 4.1, 1830),
    # --- Home & Kitchen
    ("Home & Kitchen", "Milton Thermosteel Flask 1 Litre Stainless Steel Insulated", 1249, 4.3, 24100),
    ("Home & Kitchen", "Prestige Non Stick Cookware Set 3 Pieces for New Kitchen", 2799, 4.1, 5620),
    ("Home & Kitchen", "Cello Opalware Dinner Set 18 Pieces for Home", 2199, 4.2, 8940),
    ("Home & Kitchen", "Wakefit Cotton Bedsheet Double Bed with 2 Pillow Covers", 999, 4.0, 41200),
    ("Home & Kitchen", "Pigeon Electric Kettle 1.5 Litre Stainless Steel", 899, 4.0, 33100),
    ("Home & Kitchen", "Storite Storage Organiser Set for Wardrobe Home Use", 649, 3.8, 4120),
    # --- Office Products
    ("Office Products", "Amazon Basics Adjustable Laptop Stand for Desk Aluminium", 1499, 4.3, 6210),
    ("Office Products", "Portronics Wireless Keyboard and Mouse Combo for Office Desk", 1299, 4.0, 8830),
    ("Office Products", "Callas Desk Organiser Wooden Office Stationery Holder", 899, 4.1, 1420),
    ("Office Products", "Green Soul Ergonomic Office Chair with Lumbar Support", 8999, 4.2, 12300),
    ("Office Products", "Wipro Garnet LED Desk Lamp for Study and Work From Home", 1199, 4.1, 3410),
    ("Office Products", "Zebronics USB Desk Fan Portable for Work From Home", 599, 3.9, 2280),
    # --- Badminton
    ("Badminton", "Yonex GR 303 Badminton Racquet for Beginners Aluminium", 949, 4.1, 14200),
    ("Badminton", "Li Ning Smash XP 60 Badminton Racquet Set of 2 with Cover", 1499, 4.0, 3820),
    ("Badminton", "Yonex Mavis 350 Nylon Shuttlecock Pack of 6", 899, 4.3, 9210),
    ("Badminton", "Cosco Aero 727 Badminton Shuttlecock Pack of 10 for Practice", 449, 3.9, 5610),
    ("Badminton", "Nivia Badminton Kit Bag for Racquets and Shoes", 799, 3.8, 1120),
    # --- Luggage & Travel Accessories
    ("Luggage & Travel Accessories", "Safari Pentagon Polycarbonate Trolley Suitcase 65cm Cabin", 3499, 4.1, 18200),
    ("Luggage & Travel Accessories", "American Tourister Duffle Bag 55L for Travel Water Resistant", 2299, 4.2, 6410),
    ("Luggage & Travel Accessories", "Wildcraft Travel Organiser Pouch Set of 4 Packing Cubes", 999, 4.0, 2210),
    ("Luggage & Travel Accessories", "Skybags Cabin Trolley Bag 55cm Lightweight for Short Trips", 2799, 4.0, 9120),
    ("Luggage & Travel Accessories", "Hidesign Leather Passport Holder for Travel Brown", 1999, 4.3, 480),
    ("Luggage & Travel Accessories", "Zoomlite Travel Neck Pillow Memory Foam for Flights", 1299, 3.9, 1640),
]

TIER_BOUNDS = [(0.33, "budget"), (0.67, "mid"), (0.90, "premium")]

_CAPACITY = re.compile(r"\b(\d+(?:\.\d+)?)\s*(?:l|ltr|litre|liter|litres|liters)\b", re.I)
_MATERIALS = ("leather", "cotton", "nylon", "polyester", "silk", "steel", "aluminium",
              "wooden", "ceramic", "rayon", "georgette", "woollen", "foam", "polycarbonate")
_GENDER_WORDS = [("women", r"\bwomen\b"), ("men", r"\bmen\b"), ("unisex", r"\bunisex\b")]

# category -> (product_type, use cases, seasons, occasions, gift_suitable)
CATEGORY_SEMANTICS = {
    "Rucksacks & Trekking Backpacks": ("backpack", ["trekking", "hiking", "travel"], ["all-season"], [], False),
    "Sports & Outdoor Shoes": ("shoes", ["walking", "running", "trekking"], ["all-season"], [], False),
    "Men's Winterwear": ("jacket", ["trekking", "daily wear"], ["winter"], [], False),
    "Women's Winterwear": ("jacket", ["trekking", "daily wear"], ["winter"], [], False),
    "Camping & Hiking": ("camping gear", ["camping", "trekking"], ["all-season"], [], False),
    "Women's Ethnic Wear": ("ethnic wear", ["festive", "wedding"], ["all-season"], ["wedding", "festival"], True),
    "Men's Ethnic Wear": ("ethnic wear", ["festive", "wedding"], ["all-season"], ["wedding", "festival"], True),
    "Gift Hampers": ("gift set", ["gifting"], ["all-season"], ["anniversary", "gifting", "festival"], True),
    "Headphones & Earphones": ("headphones", ["work", "calls", "music"], ["all-season"], [], True),
    "Fitness Equipment": ("fitness equipment", ["fitness", "home workout"], ["all-season"], [], False),
    "Home & Kitchen": ("home essentials", ["home", "kitchen"], ["all-season"], ["housewarming", "gifting"], True),
    "Office Products": ("office accessory", ["work", "work from home"], ["all-season"], [], False),
    "Badminton": ("badminton equipment", ["badminton", "sports"], ["all-season"], [], False),
    "Luggage & Travel Accessories": ("luggage", ["travel"], ["all-season"], [], False),
}


def raw_attributes(title: str, category: str) -> dict:
    """Read attributes off the title the way enrichment is meant to.

    Tier-B candidates are read from the title only. Tier-C values come from the
    category, which is the honest source for them: this is a fixture, and a
    fixture that invents specifications would be teaching the wrong lesson.
    """
    product_type, use_case, season, occasion, gift = CATEGORY_SEMANTICS[category]
    low = title.lower()

    capacity = _CAPACITY.search(title)
    material = next((m for m in _MATERIALS if m in low), None)
    gender = next((g for g, pattern in _GENDER_WORDS if re.search(pattern, low)), None)

    return {
        "capacity_l": float(capacity.group(1)) if capacity else None,
        "water_resistant": True if re.search(r"water[\s-]?(resistant|proof)|waterproof", low) else None,
        "gender": gender,
        "material": material,
        "product_type": product_type,
        "use_case": use_case,
        "season": season,
        "occasion": occasion,
        "gift_suitable": gift,
    }


def apply_trust_tiers(attrs: dict, source_title: str) -> dict:
    """Attach provenance, verifying tier-B claims against the source title.

    Deliberately uses the production verifiers rather than trusting the
    extraction above - a fixture built by bypassing the tier rule would hide
    exactly the bug the tier rule exists to catch.
    """
    out: dict[str, dict] = {}
    for field, value in attrs.items():
        if value is None or value == []:
            out[field] = {"value": value if value is not None else None, "source": None}
        elif field in TIER_B_FIELDS and verify(field, value, source_title):
            out[field] = {"value": value, "source": "title_verified"}
        else:
            out[field] = {"value": value, "source": "inferred"}
    return out


def assign_price_tiers(products: list[dict]) -> None:
    """Rank-based, cohort-relative. Rs 8,000 is premium for a backpack and cheap
    for a laptop, so the band comes from the price's rank within its category."""
    by_cohort: dict[str, list[dict]] = collections.defaultdict(list)
    for p in products:
        by_cohort[p["category"]].append(p)

    for cohort in by_cohort.values():
        prices = sorted(p["price"] for p in cohort)
        n = len(prices)
        for p in cohort:
            rank = bisect.bisect_left(prices, p["price"]) / (n - 1) if n > 1 else 0.0
            p["price_tier"] = next((tier for bound, tier in TIER_BOUNDS if rank < bound),
                                   "luxury")


def describe(title: str, category: str, attrs: dict) -> str:
    """A description built only from fields already present. No specifications."""
    product_type = attrs["product_type"]["value"]
    uses = ", ".join(attrs["use_case"]["value"] or []) or "everyday use"
    verified = [f"{k.replace('_', ' ')} {v['value']}" for k, v in attrs.items()
                if v["source"] == "title_verified" and k in TIER_B_FIELDS]
    sentence = f"A {product_type} listed under {category}, suited to {uses}."
    if verified:
        sentence += " The listing title states: " + "; ".join(str(v) for v in verified) + "."
    return sentence


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


def build() -> list[dict]:
    products: list[dict] = []
    for i, (category, title, price, stars, reviews) in enumerate(SEEDS):
        asin = f"B0MOCK{i:04d}"
        attrs = apply_trust_tiers(raw_attributes(title, category), title)
        product_type = attrs["product_type"]["value"]
        products.append({
            "id": asin,
            "title": title,
            "title_original": title,
            "description": describe(title, category, attrs),
            "category": category,
            "price": float(price),
            "currency": "INR",
            "rating": float(stars),
            "reviews": int(reviews),
            "quality_score": round(stars * np.log1p(reviews), 3),
            "attributes": attrs,
            "image_url": IMAGE_PLACEHOLDER + product_type.replace(" ", "+"),
            "product_url": f"https://www.amazon.in/dp/{asin}",
        })

    assign_price_tiers(products)
    return products


def _gemini_matrix(texts: list[str], model: str, dims: int) -> np.ndarray:
    """Embed with the real provider, when a key is available.

    Worth the API call: the hashing embedder has no IDF, so a title sharing
    "cotton" or "women" scores as highly as one sharing "thermal", and searching
    "thermal base layer" surfaces sarees. Real embeddings remove the one part of
    the mock stack that misrepresents how retrieval behaves.
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


def write(products: list[dict], out_dir: Path, dims: int = DIMS,
          embedder: str = "hashing") -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    with gzip.open(out_dir / "catalogue.jsonl.gz", "wt", encoding="utf-8") as f:
        for p in products:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")

    texts = [searchable_text(p) for p in products]
    if embedder == "gemini":
        model, dims = GEMINI_MODEL, GEMINI_DIMS
        matrix = _gemini_matrix(texts, model, dims)
    else:
        model = HashingEmbedding.model
        matrix = HashingEmbedding(dims=dims).encode(texts)
    np.save(out_dir / "embeddings.npy", matrix.astype(np.float16))

    # Line order in the JSONL is row order in the matrix. The manifest is what
    # makes a mismatch impossible to express silently - load_index refuses to
    # start unless the configured model and dims match these.
    (out_dir / "embeddings.manifest.json").write_text(json.dumps({
        "model": model,
        "dims": dims,
        "count": len(products),
        "normalised": True,
        "dtype": "float16",
        "built": date.today().isoformat(),
        "synthetic": True,
        "note": ("Invented products with fabricated ASINs, for running the "
                 "application without the real pipeline. Not evidence of "
                 "retrieval quality."),
    }, indent=2))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--embedder", choices=["hashing", "gemini"], default="hashing",
                        help="hashing needs no key; gemini needs GEMINI_API_KEY and "
                             "gives real semantic retrieval")
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    catalogue = build()
    write(catalogue, args.out, embedder=args.embedder)
    tiers = collections.Counter(p["price_tier"] for p in catalogue)
    print(f"wrote {len(catalogue)} products across "
          f"{len({p['category'] for p in catalogue})} categories to {args.out} "
          f"({args.embedder} embeddings)")
    print(f"price tiers: {dict(tiers)}")
