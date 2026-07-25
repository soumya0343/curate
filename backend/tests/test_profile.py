from scripts.profile_dataset import latin_fraction, passes_hygiene


def test_latin_fraction_detects_devanagari():
    assert latin_fraction("Wildcraft 45L Rucksack Trekking Backpack") > 0.85
    assert latin_fraction("पुरुषों के हैट्स और कैप्स") < 0.30


def test_hygiene_rejects_zero_price():
    row = {"title": "A perfectly reasonable product title here", "price": "0.0"}
    assert passes_hygiene(row) is False


def test_hygiene_rejects_short_title():
    assert passes_hygiene({"title": "Cap", "price": "299.0"}) is False


def test_hygiene_rejects_devanagari_title():
    row = {"title": "प्लेन कैज़ुअल वियर बेसबॉल कैप पुरुषों और महिलाओं", "price": "299.0"}
    assert passes_hygiene(row) is False


def test_hygiene_accepts_valid_row():
    row = {"title": "Wildcraft 45L Rucksack Water Resistant Trekking Backpack",
           "price": "3499.0"}
    assert passes_hygiene(row) is True
