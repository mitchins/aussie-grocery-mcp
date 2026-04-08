import pytest

import main


def test_fmt_product_maps_fields():
    raw = {
        "Stockcode": 41402,
        "UrlFriendlyName": "bulla-cottage-cheese-original",
        "Name": "Bulla Cottage Cheese Original",
        "Brand": "Bulla",
        "Price": 4.2,
        "IsAvailable": True,
        "PackageSize": "200g",
    }

    result = main._fmt_product(raw)

    assert result["stockcode"] == 41402
    assert result["name"] == "Bulla Cottage Cheese Original"
    assert result["brand"] == "Bulla"
    assert result["price"] == pytest.approx(4.2)
    assert result["is_available"] is True
    assert result["package_size"] == "200g"
    assert result["url"].endswith("/41402/bulla-cottage-cheese-original")


def test_parse_nutrition_returns_none_when_missing_payload():
    detail = {"AdditionalAttributes": {}}
    assert main._parse_nutrition(detail) is None


def test_parse_nutrition_extracts_attributes_dict_payload():
    detail = {
        "Name": "Bulla Cottage Cheese Original",
        "Stockcode": 41402,
        "AdditionalAttributes": {
            "nutritionalinformation": {
                "Attributes": [
                    {
                        "Name": "Sodium Quantity Per 100g - Total - NIP",
                        "Value": "312.0mg",
                    },
                    {
                        "Name": "Protein Quantity Per 100g - Total - NIP",
                        "Value": "12.0g",
                    },
                ]
            },
            "ingredients": "Milk, Cream",
            "allergystatement": "Contains milk",
            "healthstarrating": "4.5",
        },
    }

    result = main._parse_nutrition(detail)

    assert result is not None
    assert result["product_name"] == "Bulla Cottage Cheese Original"
    assert result["stockcode"] == 41402
    assert result["nutrition"]["Sodium Quantity Per 100g - Total - NIP"] == "312.0mg"
    assert result["ingredients"] == "Milk, Cream"
    assert result["allergystatement"] == "Contains milk"
    assert result["healthstarrating"] == "4.5"
