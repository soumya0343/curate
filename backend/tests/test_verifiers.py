from scripts.verify_attributes import TIER_B_FIELDS, verify

TITLE = "Wildcraft 45L Rucksack Water Resistant Trekking Backpack"


def test_capacity_verified_when_present():
    assert verify("capacity_l", 45, TITLE) is True


def test_capacity_rejected_when_absent():
    assert verify("capacity_l", 60, TITLE) is False


def test_water_resistant_verified():
    assert verify("water_resistant", True, TITLE) is True


def test_water_resistant_rejected_on_silent_title():
    assert verify("water_resistant", True, "Wildcraft 45L Rucksack Backpack") is False


def test_gender_verified_from_title():
    assert verify("gender", "women", "Puma Running Shoes for Women Size 7") is True


def test_gender_rejected_when_only_inferred():
    assert verify("gender", "women", "Puma Running Shoes Size 7") is False


def test_material_verified():
    assert verify("material", "leather", "Hidesign Leather Wallet for Men") is True


def test_unknown_field_is_never_verified():
    assert verify("temp_rating_c", -12, TITLE) is False


def test_false_value_needs_no_verification():
    # Absence claims are safe: a False water_resistant excludes nothing.
    assert verify("water_resistant", False, TITLE) is True


def test_tier_b_fields_are_exactly_the_verifiable_ones():
    assert TIER_B_FIELDS == frozenset(
        {"capacity_l", "water_resistant", "gender", "material", "brand", "pack_count"})


def test_brand_verified_from_title():
    assert verify("brand", "Wildcraft", TITLE) is True


def test_brand_rejected_when_absent():
    assert verify("brand", "Nike", TITLE) is False


def test_pack_count_verified_from_title():
    assert verify("pack_count", 6, "8 Pack Neck Gaiter Face Mask") is False
    assert verify("pack_count", 8, "8 Pack Neck Gaiter Face Mask") is True


def test_pack_count_rejected_when_absent():
    assert verify("pack_count", 4, TITLE) is False
