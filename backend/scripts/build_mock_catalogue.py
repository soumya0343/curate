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
import re
import sys
import urllib.parse
from pathlib import Path

import numpy as np

# `python scripts/build_mock_catalogue.py` puts scripts/ on sys.path, not the
# backend root, so `app` and `scripts` are both unimportable without this.
# pytest gets it from pytest.ini's `pythonpath = .`; a direct run does not.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import catalogue_build  # noqa: E402
from scripts.verify_attributes import TIER_B_FIELDS  # noqa: E402

DIMS = 256
OUT_DIR = Path("data/mock")
# Real Unsplash CDN photos, HEAD-verified to return 200 with an image/*
# content-type. 2-4 distinct photos per category so products in the same
# category don't all show the identical picture; `_image_url` below picks one
# deterministically per product so rebuilds are stable.
CATEGORY_IMAGES: dict[str, list[str]] = {
    "Rucksacks & Trekking Backpacks": [
        "https://images.unsplash.com/photo-1553062407-98eeb64c6a62?w=400&h=400&fit=crop",
        "https://images.unsplash.com/photo-1551632811-561732d1e306?w=400&h=400&fit=crop",
        "https://images.unsplash.com/photo-1501555088652-021faa106b9b?w=400&h=400&fit=crop",
    ],
    "Sports & Outdoor Shoes": [
        "https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=400&h=400&fit=crop",
        "https://images.unsplash.com/photo-1606107557195-0e29a4b5b4aa?w=400&h=400&fit=crop",
        "https://images.unsplash.com/photo-1571008887538-b36bb32f4571?w=400&h=400&fit=crop",
    ],
    "Men's Winterwear": [
        "https://images.unsplash.com/photo-1624548140129-74786c5f1279?w=400&h=400&fit=crop",
        "https://images.unsplash.com/photo-1624548140150-108c3287f551?w=400&h=400&fit=crop",
        "https://images.unsplash.com/photo-1644767128311-9b3d8f936613?w=400&h=400&fit=crop",
    ],
    "Women's Winterwear": [
        "https://images.unsplash.com/photo-1637496462702-f8949d68ab11?w=400&h=400&fit=crop",
        "https://images.unsplash.com/photo-1678884399113-0a2b079a31f5?w=400&h=400&fit=crop",
        "https://images.unsplash.com/photo-1636529109797-0749811c4916?w=400&h=400&fit=crop",
    ],
    "Camping & Hiking": [
        "https://images.unsplash.com/photo-1504280390367-361c6d9f38f4?w=400&h=400&fit=crop",
        "https://images.unsplash.com/photo-1631635589499-afd87d52bf64?w=400&h=400&fit=crop",
        "https://images.unsplash.com/photo-1576176539998-0237d1ac6a85?w=400&h=400&fit=crop",
    ],
    "Women's Ethnic Wear": [
        "https://images.unsplash.com/photo-1610030469983-98e550d6193c?w=400&h=400&fit=crop",
        "https://images.unsplash.com/photo-1622049605334-72e1e4432346?w=400&h=400&fit=crop",
        "https://images.unsplash.com/photo-1631005436794-ccaa79de61ba?w=400&h=400&fit=crop",
    ],
    "Men's Ethnic Wear": [
        "https://images.unsplash.com/photo-1583391733956-3750e0ff4e8b?w=400&h=400&fit=crop",
        "https://images.unsplash.com/photo-1727835523545-70ee992b5763?w=400&h=400&fit=crop",
        "https://images.unsplash.com/photo-1727835523550-18478cacefa2?w=400&h=400&fit=crop",
    ],
    "Gift Hampers": [
        "https://images.unsplash.com/photo-1549465220-1a8b9238cd48?w=400&h=400&fit=crop",
        "https://images.unsplash.com/photo-1513201099705-a9746e1e201f?w=400&h=400&fit=crop",
        "https://images.unsplash.com/photo-1592903297149-37fb25202dfa?w=400&h=400&fit=crop",
    ],
    "Headphones & Earphones": [
        "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=400&h=400&fit=crop",
        "https://images.unsplash.com/photo-1618366712010-f4ae9c647dcb?w=400&h=400&fit=crop",
        "https://images.unsplash.com/photo-1546435770-a3e426bf472b?w=400&h=400&fit=crop",
    ],
    "Fitness Equipment": [
        "https://images.unsplash.com/photo-1517836357463-d25dfeac3438?w=400&h=400&fit=crop",
        "https://images.unsplash.com/photo-1534438327276-14e5300c3a48?w=400&h=400&fit=crop",
        "https://images.unsplash.com/photo-1571902943202-507ec2618e8f?w=400&h=400&fit=crop",
    ],
    "Home & Kitchen": [
        "https://images.unsplash.com/photo-1556909114-f6e7ad7d3136?w=400&h=400&fit=crop",
        "https://images.unsplash.com/photo-1556911220-e15b29be8c8f?w=400&h=400&fit=crop",
        "https://images.unsplash.com/photo-1556910096-6f5e72db6803?w=400&h=400&fit=crop",
    ],
    "Office Products": [
        "https://images.unsplash.com/photo-1593642632559-0c6d3fc62b89?w=400&h=400&fit=crop",
        "https://images.unsplash.com/photo-1535957998253-26ae1ef29506?w=400&h=400&fit=crop",
        "https://images.unsplash.com/photo-1531347334762-59780ece5c76?w=400&h=400&fit=crop",
    ],
    "Badminton": [
        "https://images.unsplash.com/photo-1626224583764-f87db24ac4ea?w=400&h=400&fit=crop",
        "https://images.unsplash.com/photo-1708312604109-16c0be9326cd?w=400&h=400&fit=crop",
        "https://images.unsplash.com/photo-1687597778602-624a9438fe0b?w=400&h=400&fit=crop",
    ],
    "Luggage & Travel Accessories": [
        "https://images.unsplash.com/photo-1581553680321-4fffae59fccd?w=400&h=400&fit=crop",
        "https://images.unsplash.com/photo-1504150558240-0b4fd8946624?w=400&h=400&fit=crop",
        "https://images.unsplash.com/photo-1473625247510-8ceb1760943f?w=400&h=400&fit=crop",
    ],
    "Men's Casual Wear": [
        "https://images.unsplash.com/photo-1516257984-b1b4d707412e?w=400&h=400&fit=crop",
        "https://images.unsplash.com/photo-1617114919297-3c8ddb01f599?w=400&h=400&fit=crop",
        "https://images.unsplash.com/photo-1479064555552-3ef4979f8908?w=400&h=400&fit=crop",
    ],
    "Women's Casual Wear": [
        "https://images.unsplash.com/photo-1515886657613-9f3515b0c78f?w=400&h=400&fit=crop",
        "https://images.unsplash.com/photo-1609091289242-735df7a2207a?w=400&h=400&fit=crop",
        "https://images.unsplash.com/photo-1626948683538-fed29f226292?w=400&h=400&fit=crop",
    ],
    "Sunglasses & Eyewear": [
        "https://images.unsplash.com/photo-1511499767150-a48a237f0083?w=400&h=400&fit=crop",
        "https://images.unsplash.com/photo-1577803645773-f96470509666?w=400&h=400&fit=crop",
        "https://images.unsplash.com/photo-1596993100471-c3905dafa78e?w=400&h=400&fit=crop",
    ],
    "Skincare & Beauty": [
        "https://images.unsplash.com/photo-1571781926291-c477ebfd024b?w=400&h=400&fit=crop",
        "https://images.unsplash.com/photo-1580870069867-74c57ee1bb07?w=400&h=400&fit=crop",
        "https://images.unsplash.com/photo-1585945037805-5fd82c2e60b1?w=400&h=400&fit=crop",
    ],
    "Smartphones & Accessories": [
        "https://images.unsplash.com/photo-1511707171634-5f897ff02aa9?w=400&h=400&fit=crop",
        "https://images.unsplash.com/photo-1592890288564-76628a30a657?w=400&h=400&fit=crop",
        "https://images.unsplash.com/photo-1598327105666-5b89351aff97?w=400&h=400&fit=crop",
    ],
    "Books": [
        "https://images.unsplash.com/photo-1512820790803-83ca734da794?w=400&h=400&fit=crop",
        "https://images.unsplash.com/photo-1497633762265-9d179a990aa6?w=400&h=400&fit=crop",
        "https://images.unsplash.com/photo-1495446815901-a7297e633e8d?w=400&h=400&fit=crop",
    ],
    "Jewellery & Accessories": [
        "https://images.unsplash.com/photo-1515562141207-7a88fb7ce338?w=400&h=400&fit=crop",
        "https://images.unsplash.com/photo-1617038220319-276d3cfab638?w=400&h=400&fit=crop",
        "https://images.unsplash.com/photo-1633934542430-0905ccb5f050?w=400&h=400&fit=crop",
    ],
    "Monsoon & Rain Gear": [
        "https://images.unsplash.com/photo-1428592953211-077101b2021b?w=400&h=400&fit=crop",
        "https://images.unsplash.com/photo-1519692933481-e162a57d6721?w=400&h=400&fit=crop",
        "https://images.unsplash.com/photo-1523772721666-22ad3c3b6f90?w=400&h=400&fit=crop",
    ],
    "Men's Footwear": [
        "https://images.unsplash.com/photo-1491553895911-0055eca6402d?w=400&h=400&fit=crop",
        "https://images.unsplash.com/photo-1668069226492-508742b03147?w=400&h=400&fit=crop",
        "https://images.unsplash.com/photo-1616406432452-07bc5938759d?w=400&h=400&fit=crop",
    ],
    "Women's Footwear": [
        "https://images.unsplash.com/photo-1543163521-1bf539c55dd2?w=400&h=400&fit=crop",
        "https://images.unsplash.com/photo-1704775989614-8435994e4e97?w=400&h=400&fit=crop",
        "https://images.unsplash.com/photo-1562273138-f46be4ebdf33?w=400&h=400&fit=crop",
    ],
    "Cricket": [
        "https://images.unsplash.com/photo-1531415074968-036ba1b575da?w=400&h=400&fit=crop",
        "https://images.unsplash.com/photo-1593341646782-e0b495cff86d?w=400&h=400&fit=crop",
        "https://images.unsplash.com/photo-1595210382266-2d0077c1f541?w=400&h=400&fit=crop",
    ],
}


def _image_url(category: str, index_in_category: int) -> str:
    """Deterministic per-product photo pick: same input, same output, every
    rebuild - required for the artifacts to be reproducible.

    A category present in SEEDS but absent here is a fixture bug, not
    something to paper over with a placeholder, so it raises rather than
    falling back silently.
    """
    urls = CATEGORY_IMAGES.get(category)
    if not urls:
        raise KeyError(f"No CATEGORY_IMAGES entry for category {category!r}; "
                        "add at least one Unsplash photo URL for it.")
    return urls[index_in_category % len(urls)]

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
    ("Men's Winterwear", "Puma Hooded Zip Up Sweatshirt for Men Water Resistant Winter Wear", 1799, 4.0, 2210),
    ("Men's Winterwear", "The North Face Alpine Down Jacket for Men Windproof Water Resistant", 8999, 4.5, 340),
    ("Women's Winterwear", "Monte Carlo Woollen Cardigan for Women Winter Wear", 2299, 4.2, 890),
    ("Women's Winterwear", "Decathlon Quechua Fleece Jacket for Women Warm Trekking Layer", 1599, 4.3, 1120),
    ("Women's Winterwear", "Jockey Thermal Leggings for Women Cotton Winter Base Layer", 949, 4.0, 2210),
    ("Women's Winterwear", "Fabindia Cotton Shawl for Women Winter Wear Handloom", 1299, 3.9, 480),
    ("Women's Winterwear", "H&M Woollen Overcoat for Women Winter Formal Wear", 3799, 4.2, 610),
    ("Women's Winterwear", "Woodland Water Resistant Parka Jacket for Women Olive", 5499, 4.3, 290),
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
    ("Men's Ethnic Wear", "Fabindia Cotton Kurta for Men Casual Ethnic Wear White", 1599, 4.0, 1420),
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
    ("Badminton", "Yonex Astrox 88D Pro Badminton Racquet for Advanced Players", 12999, 4.4, 210),
    # --- Luggage & Travel Accessories
    ("Luggage & Travel Accessories", "Safari Pentagon Polycarbonate Trolley Suitcase 65cm Cabin", 3499, 4.1, 18200),
    ("Luggage & Travel Accessories", "American Tourister Duffle Bag 55L for Travel Water Resistant", 2299, 4.2, 6410),
    ("Luggage & Travel Accessories", "Wildcraft Travel Organiser Pouch Set of 4 Packing Cubes", 999, 4.0, 2210),
    ("Luggage & Travel Accessories", "Skybags Cabin Trolley Bag 55cm Lightweight for Short Trips", 2799, 4.0, 9120),
    ("Luggage & Travel Accessories", "Hidesign Leather Passport Holder for Travel Brown", 1999, 4.3, 480),
    ("Luggage & Travel Accessories", "Zoomlite Travel Neck Pillow Memory Foam for Flights", 1299, 3.9, 1640),
    # --- Men's Casual Wear
    ("Men's Casual Wear", "Levis 511 Slim Fit Jeans for Men Mid Rise Blue", 3499, 4.3, 18400),
    ("Men's Casual Wear", "Allen Solly Regular Fit Casual Shirt for Men Cotton", 1299, 4.1, 9210),
    ("Men's Casual Wear", "H&M Slim Fit Chinos for Men Beige Cotton Stretch", 1799, 4.0, 6400),
    ("Men's Casual Wear", "Puma Graphic Tee for Men Cotton Crew Neck", 799, 4.2, 21100),
    ("Men's Casual Wear", "Raymond Men's Regular Fit Formal Trousers Polyester Viscose", 2299, 4.1, 4320),
    ("Men's Casual Wear", "US Polo Assn Polo T Shirt for Men Cotton Pique", 1499, 4.3, 31200),
    ("Men's Casual Wear", "Jack Jones Casual Bomber Jacket for Men Lightweight", 2999, 4.2, 2810),
    # --- Women's Casual Wear
    ("Women's Casual Wear", "H&M High Waist Straight Jeans for Women Blue Denim", 2999, 4.2, 12100),
    ("Women's Casual Wear", "Zara Basic Linen Blend Shirt for Women White", 2299, 4.1, 5430),
    ("Women's Casual Wear", "Mango Floral Printed Wrap Dress for Women Rayon", 3499, 4.3, 3210),
    ("Women's Casual Wear", "Global Desi Printed Casual Kurti for Women Cotton Blend", 899, 4.0, 14200),
    ("Women's Casual Wear", "Biba Cotton Palazzo Pants for Women Ethnic Casual Wear", 1199, 4.1, 8900),
    ("Women's Casual Wear", "ONLY Regular Fit Sweatshirt for Women Fleece Hooded", 1799, 4.2, 6100),
    # --- Sunglasses & Eyewear
    ("Sunglasses & Eyewear", "Ray Ban Aviator Classic Sunglasses for Men UV Protection", 6990, 4.5, 8920),
    ("Sunglasses & Eyewear", "Fastrack UV Protected Wayfarer Sunglasses for Men Black", 1299, 4.2, 14300),
    ("Sunglasses & Eyewear", "Titan Glares UV400 Rectangular Sunglasses for Women Brown", 1799, 4.1, 5610),
    ("Sunglasses & Eyewear", "Bolon Polarised Pilot Sunglasses for Driving Men", 2499, 4.3, 2100),
    ("Sunglasses & Eyewear", "Voyage Black Rimmed Round Sunglasses for Women Lightweight", 999, 4.0, 9800),
    ("Sunglasses & Eyewear", "Fastrack Polycarbonate Square Sunglasses for Men Budget Friendly", 449, 3.8, 6200),
    # --- Skincare & Beauty
    ("Skincare & Beauty", "Minimalist 10 percent Niacinamide Face Serum for Men Women 30ml", 699, 4.4, 48200),
    ("Skincare & Beauty", "Dot and Key Vitamin C Brightening Moisturiser SPF 50 for Women", 899, 4.3, 21300),
    ("Skincare & Beauty", "Mamaearth Ubtan Face Wash for Oily Skin 100ml Natural", 299, 4.1, 62100),
    ("Skincare & Beauty", "Forest Essentials Facial Tonic Mist Rose and Niacinamide 50ml", 1650, 4.5, 4800),
    ("Skincare & Beauty", "Plum Grape Seed and Sea Buckthorn Face Cream SPF 35 for Women", 549, 4.2, 18400),
    ("Skincare & Beauty", "Kama Ayurveda Kumkumadi Miraculous Beauty Fluid Night Serum 12ml", 2750, 4.4, 3200),
    ("Skincare & Beauty", "Neutrogena Deep Moisture Body Lotion for Dry Skin 400ml", 799, 4.3, 29100),
    # --- Smartphones & Accessories
    ("Smartphones & Accessories", "Redmi Note 13 Pro 5G 8GB 256GB Midnight Black", 28999, 4.3, 41200),
    ("Smartphones & Accessories", "Samsung Galaxy M34 5G 6GB 128GB Midnight Blue", 18999, 4.2, 32100),
    ("Smartphones & Accessories", "boAt Rugged v3 Braided Micro USB Cable 1.5m for Android", 349, 4.0, 88200),
    ("Smartphones & Accessories", "Spigen Thin Fit Case for iPhone 15 Slim Hard Back Cover", 1499, 4.4, 9100),
    ("Smartphones & Accessories", "Anker 65W GaN Charger USB C Fast Charging for Laptops Phones", 2799, 4.5, 14300),
    ("Smartphones & Accessories", "OnePlus Nord CE3 Lite 5G 8GB 128GB Chromatic Gray", 19999, 4.1, 22400),
    ("Smartphones & Accessories", "Belkin Magnetic Wireless Charger 15W for iPhone MagSafe", 3499, 4.3, 5600),
    # --- Books
    ("Books", "Atomic Habits James Clear Paperback Self Improvement", 399, 4.7, 92100),
    ("Books", "The Psychology of Money Morgan Housel Paperback Finance", 349, 4.6, 71300),
    ("Books", "Ikigai Hector Garcia Francesc Miralles Paperback Lifestyle", 299, 4.5, 54200),
    ("Books", "Rich Dad Poor Dad Robert Kiyosaki Paperback Personal Finance", 249, 4.4, 88400),
    ("Books", "The Almanack of Naval Ravikant Eric Jorgenson Paperback", 349, 4.6, 41200),
    ("Books", "Sapiens A Brief History of Humankind Yuval Noah Harari Paperback", 499, 4.6, 67800),
    ("Books", "Zero to One Peter Thiel Blake Masters Paperback Entrepreneurship", 399, 4.5, 38100),
    # --- Jewellery & Accessories
    ("Jewellery & Accessories", "Malabar Gold 22KT Yellow Gold Ring for Women Wedding", 32000, 4.5, 1820),
    ("Jewellery & Accessories", "Tanishq Silver Bracelet for Women 925 Sterling Hallmarked", 4999, 4.4, 3210),
    ("Jewellery & Accessories", "Pipa Bella Gold Plated Choker Necklace for Women Festive Wear", 1299, 4.2, 8400),
    ("Jewellery & Accessories", "Zaveri Pearls Kundan Earrings for Women Wedding Ethnic Wear", 699, 4.1, 11200),
    ("Jewellery & Accessories", "Orra Diamond Pendant Necklace for Women 18KT Gold Anniversary", 24999, 4.6, 420),
    ("Jewellery & Accessories", "Fastrack Analog Wrist Watch for Women Rose Gold Strap", 2299, 4.3, 6800),
    # --- Monsoon & Rain Gear
    ("Monsoon & Rain Gear", "Wildcraft Compact Rain Jacket Waterproof Windproof for Men", 2499, 4.2, 3210),
    ("Monsoon & Rain Gear", "Trespass Packaway Rain Jacket for Women Waterproof Lightweight", 3299, 4.3, 1840),
    ("Monsoon & Rain Gear", "Decathlon Quechua Waterproof Rain Poncho Unisex Compact", 999, 4.1, 4200),
    ("Monsoon & Rain Gear", "Instafit Waterproof Rain Pants for Men Trekking Monsoon", 1499, 4.0, 2100),
    ("Monsoon & Rain Gear", "Bata Comfit Waterproof Rain Boots for Men Anti Skid Black", 2199, 4.1, 1600),
    ("Monsoon & Rain Gear", "Rainco Windproof Travel Umbrella Compact Auto Open Close", 799, 4.0, 9800),
    ("Monsoon & Rain Gear", "Decathlon Artengo Waterproof Backpack Rain Cover 20-30L", 649, 4.2, 3100),
    # --- Men's Footwear
    ("Men's Footwear", "Red Tape Leather Formal Derby Shoes for Men Black", 2999, 4.2, 8400),
    ("Men's Footwear", "Clarks Desert Boot Leather Casual Shoes for Men Tan", 7999, 4.5, 3210),
    ("Men's Footwear", "Woodland Leather Casual Shoes for Men Khaki", 3799, 4.2, 6100),
    ("Men's Footwear", "Sparx Casual Sandals for Men EVA Lightweight", 849, 4.0, 14200),
    ("Men's Footwear", "Adidas Adilette Slide Sandals for Men White Black", 1999, 4.3, 11300),
    ("Men's Footwear", "Bata Comfort Formal Leather Shoes for Men Black Office Wear", 1399, 3.9, 5200),
    # --- Women's Footwear
    ("Women's Footwear", "Metro Textured Block Heel Sandals for Women Nude", 1799, 4.1, 6800),
    ("Women's Footwear", "Steve Madden Leather Heeled Sandals for Women Gold Festive", 4999, 4.4, 2100),
    ("Women's Footwear", "Catwalk Pointed Toe Stiletto Heels for Women Black", 2499, 4.2, 4300),
    ("Women's Footwear", "Bata Mary Jane Flats for Women Comfortable Daily Wear", 1299, 4.0, 9200),
    ("Women's Footwear", "Crocs Classic Clogs for Women Lightweight Casual", 3499, 4.4, 18100),
    ("Women's Footwear", "Relaxo Flite Slippers for Women Comfortable Daily Wear", 799, 3.9, 8100),
    # --- Cricket
    ("Cricket", "SG Sunny Tonny Kashmir Willow Cricket Bat for Beginners", 1499, 4.1, 6200),
    ("Cricket", "Kookaburra Pace 3.0 English Willow Cricket Bat Men", 8999, 4.4, 1800),
    ("Cricket", "SS Ton Reserve Edition English Willow Cricket Bat", 14999, 4.5, 620),
    ("Cricket", "Cosco Cricket Tennis Ball Pack of 6 Red", 399, 4.0, 21200),
    ("Cricket", "SG Batting Gloves for Men RH Premium Leather", 1299, 4.2, 3400),
    ("Cricket", "Nike Cricket Shoes Rubber Spikes for Men White", 3499, 4.3, 2100),
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
    "Men's Casual Wear": ("casual wear", ["daily wear", "casual"], ["all-season"], [], False),
    "Women's Casual Wear": ("casual wear", ["daily wear", "casual"], ["all-season"], [], False),
    "Sunglasses & Eyewear": ("sunglasses", ["daily wear", "outdoor", "travel"], ["all-season"], [], True),
    "Skincare & Beauty": ("skincare", ["daily care", "gifting"], ["all-season"], ["anniversary", "gifting"], True),
    "Smartphones & Accessories": ("smartphone", ["work", "daily use", "tech"], ["all-season"], [], True),
    "Books": ("book", ["reading", "learning", "gifting"], ["all-season"], ["gifting"], True),
    "Jewellery & Accessories": ("jewellery", ["wedding", "festive", "daily wear"], ["all-season"], ["wedding", "anniversary", "festival"], True),
    "Monsoon & Rain Gear": ("rain gear", ["trekking", "daily wear", "travel"], ["monsoon"], [], False),
    "Men's Footwear": ("footwear", ["daily wear", "formal", "casual"], ["all-season"], [], False),
    "Women's Footwear": ("footwear", ["daily wear", "festive", "casual"], ["all-season"], ["wedding", "festival"], False),
    "Cricket": ("cricket equipment", ["cricket", "sports"], ["all-season"], [], False),
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


def build() -> list[dict]:
    products: list[dict] = []
    category_seen: dict[str, int] = collections.defaultdict(int)
    for i, (category, title, price, stars, reviews) in enumerate(SEEDS):
        asin = f"B0MOCK{i:04d}"
        attrs = catalogue_build.apply_trust_tiers(
            raw_attributes(title, category), title, TIER_B_FIELDS)
        index_in_category = category_seen[category]
        category_seen[category] += 1
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
            "image_url": _image_url(category, index_in_category),
            # The ASIN is fabricated, so /dp/{asin} would 404 on every card.
            # A search link resolves to something real, which is the honest
            # option for invented data (tests/test_mock_stack.py).
            "product_url": ("https://www.amazon.in/s?k="
                            + urllib.parse.quote_plus(title)),
        })

    assign_price_tiers(products)
    return products


def write(products: list[dict], out_dir: Path, dims: int = DIMS,
          embedder: str = "hashing") -> None:
    catalogue_build.write(
        products, out_dir, dims=dims, embedder=embedder, synthetic=True,
        note=("Invented products with fabricated ASINs, for running the "
              "application without the real pipeline. Not evidence of "
              "retrieval quality."))


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
