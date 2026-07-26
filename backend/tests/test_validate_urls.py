from scripts.validate_urls import assert_structure


def test_clean_product_list_passes():
    products = [
        {
            "id": "B0ABC12345",
            "product_url": "https://www.amazon.in/dp/B0ABC12345",
            "image_url": "https://m.media-amazon.com/images/I/abc.jpg",
        },
        {
            "id": "B0XYZ98765",
            "product_url": "https://www.amazon.in/dp/B0XYZ98765",
            "image_url": "https://m.media-amazon.com/images/I/xyz.jpg",
        },
    ]

    summary = assert_structure(products)

    assert summary == {"checked": 2, "malformed": [], "duplicate_ids": []}


def test_product_url_not_matching_id_is_reported_as_malformed():
    products = [
        {
            "id": "B0ABC12345",
            "product_url": "https://www.amazon.in/dp/B0WRONGID",
            "image_url": "https://m.media-amazon.com/images/I/abc.jpg",
        },
    ]

    summary = assert_structure(products)

    assert summary["checked"] == 1
    assert summary["malformed"] == ["B0ABC12345"]
    assert summary["duplicate_ids"] == []


def test_missing_or_empty_image_url_is_reported_as_malformed():
    products = [
        {
            "id": "B0ABC12345",
            "product_url": "https://www.amazon.in/dp/B0ABC12345",
            "image_url": "",
        },
        {
            "id": "B0NOIMAGE1",
            "product_url": "https://www.amazon.in/dp/B0NOIMAGE1",
            "image_url": "http://not-https.example.com/img.jpg",
        },
    ]

    summary = assert_structure(products)

    assert summary["checked"] == 2
    assert set(summary["malformed"]) == {"B0ABC12345", "B0NOIMAGE1"}


def test_duplicate_ids_are_reported():
    products = [
        {
            "id": "B0DUPE0001",
            "product_url": "https://www.amazon.in/dp/B0DUPE0001",
            "image_url": "https://m.media-amazon.com/images/I/one.jpg",
        },
        {
            "id": "B0DUPE0001",
            "product_url": "https://www.amazon.in/dp/B0DUPE0001",
            "image_url": "https://m.media-amazon.com/images/I/two.jpg",
        },
        {
            "id": "B0UNIQUE01",
            "product_url": "https://www.amazon.in/dp/B0UNIQUE01",
            "image_url": "https://m.media-amazon.com/images/I/three.jpg",
        },
    ]

    summary = assert_structure(products)

    assert summary["checked"] == 3
    assert summary["malformed"] == []
    assert summary["duplicate_ids"] == ["B0DUPE0001"]
