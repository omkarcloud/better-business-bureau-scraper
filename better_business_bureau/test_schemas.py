"""Offline tests for the /better-business-bureau/* request schemas and
reference resolvers.

    python -m pytest better_business_bureau/test_schemas.py -q
"""
import os
import sys

import pytest
from marshmallow import ValidationError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from better_business_bureau import refs, schemas  # noqa: E402


# ---- refs ---------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("1296-7039385", "1296-7039385"),
    (" 1296_7039385 ", "1296-7039385"),
    ("https://www.bbb.org/us/wa/seattle/profile/ecommerce/amazoncom-1296-7039385", "1296-7039385"),
    ("https://www.bbb.org/us/wa/seattle/profile/ecommerce/amazoncom-1296-7039385/customer-reviews?page=2", "1296-7039385"),
    ("https://www.bbb.org/ca/on/east-york/profile/home-improvement/jackson-associates-inc-0107-1131634/complaints", "0107-1131634"),
    ("//www.bbb.org/us/il/chicago/profile/general-contractor/sullivan-lane-inc-0654-1000012025", "0654-1000012025"),
])
def test_resolve_company(value, expected):
    assert refs.resolve_company(value) == expected


def test_resolve_company_link_seeds_the_canonical_path():
    refs.resolve_company("https://www.bbb.org/us/wa/seattle/profile/ecommerce/amazoncom-1296-7039385/complaints?page=3")
    assert refs.known_profile_path("1296-7039385") == "/us/wa/seattle/profile/ecommerce/amazoncom-1296-7039385"


@pytest.mark.parametrize("value", ["", "amazon", "7039385", "1296-", "https://example.com/profile/x/x-1296-7039385",
                                   "https://www.bbb.org/search?find_text=amazon"])
def test_resolve_company_rejects(value):
    with pytest.raises(ValueError):
        refs.resolve_company(value)


@pytest.mark.parametrize("value,expected", [
    ("10113-000", "10113-000"),
    ("plumber", "plumber"),
    ("Roofing Contractors", "roofing-contractors"),
    ("https://www.bbb.org/us/category/plumber", "plumber"),
    ("https://www.bbb.org/us/il/chicago/category/sewer-cleaning/accredited", "sewer-cleaning"),
])
def test_resolve_category(value, expected):
    assert refs.resolve_category(value) == expected


@pytest.mark.parametrize("value", ["", "plumb er!", "https://example.com/category/plumber",
                                   "https://www.bbb.org/us/il/chicago"])
def test_resolve_category_rejects(value):
    with pytest.raises(ValueError):
        refs.resolve_category(value)


def test_stub_path_uses_a_real_state():
    assert refs.stub_profile_path("1296-7039385") == "/us/ca/city/profile/business/business-1296-7039385"


# ---- schemas ------------------------------------------------------------------

def test_company_schema_accepts_id_and_link():
    assert schemas.CompanySchema().load({"company": "1296-7039385"}) == {"company": "1296-7039385"}
    loaded = schemas.CompanySchema().load(
        {"company": "https://www.bbb.org/us/wa/seattle/profile/ecommerce/amazoncom-1296-7039385"})
    assert loaded == {"company": "1296-7039385"}


@pytest.mark.parametrize("value", ["", "amazon", "https://example.com/x-1296-7039385"])
def test_company_schema_rejects(value):
    with pytest.raises(ValidationError) as e:
        schemas.CompanySchema().load({"company": value})
    assert "company" in e.value.messages


def test_company_schema_rejects_sibling_params():
    with pytest.raises(ValidationError):
        schemas.CompanySchema().load({"company": "1296-7039385", "url": "x"})


def test_search_schema_defaults():
    loaded = schemas.CompaniesSearchSchema().load({"query": " plumber "})
    assert loaded == {"query": "plumber", "location": None, "country": "USA", "page": 1, "sort": "Relevance",
                      "rating": None, "state": None, "distance": None, "accredited_only": False,
                      "quote_requests_only": False, "serving_area_only": False, "search_type": None,
                      "category": None}


def test_search_schema_maps_tokens():
    loaded = schemas.CompaniesSearchSchema().load({
        "query": "plumber", "location": "Chicago, IL", "country": "CA", "page": "3", "sort": "name_desc",
        "rating": "a", "state": "il", "distance": "25", "accredited_only": "yes", "quote_requests_only": "1",
        "serving_area_only": "true", "search_type": "Name", "category": "10113-000"})
    assert loaded["country"] == "CAN"
    assert loaded["page"] == 3
    assert loaded["sort"] == "ZToA"
    assert loaded["rating"] == "A"
    assert loaded["state"] == "IL"
    assert loaded["distance"] == "25"
    assert loaded["accredited_only"] is True and loaded["quote_requests_only"] is True
    assert loaded["serving_area_only"] is True
    assert loaded["search_type"] == "Name"
    assert loaded["category"] == "10113-000"


@pytest.mark.parametrize("params,field", [
    ({}, "query"),
    ({"query": "x", "page": "16"}, "page"),
    ({"query": "x", "sort": "popular"}, "sort"),
    ({"query": "x", "rating": "A+"}, "rating"),
    ({"query": "x", "distance": "7", "location": "Chicago, IL"}, "distance"),
    ({"query": "x", "distance": "5"}, "distance"),
    ({"query": "x", "sort": "distance"}, "sort"),
    ({"query": "x", "state": "Illinois"}, "state"),
    ({"query": "x", "country": "uk"}, "country"),
    ({"query": "x", "category": "plumber"}, "category"),
    ({"query": "x", "accredited_only": "maybe"}, "accredited_only"),
    ({"query": "x", "url": "y"}, "url"),
])
def test_search_schema_rejects(params, field):
    with pytest.raises(ValidationError) as e:
        schemas.CompaniesSearchSchema().load(params)
    assert field in e.value.messages


def test_categories_search_schema():
    loaded = schemas.CategoriesSearchSchema().load({"category": "https://www.bbb.org/us/category/plumber",
                                                    "location": "60639", "accredited_only": "true"})
    assert loaded["category"] == "plumber"
    assert loaded["location"] == "60639" and loaded["accredited_only"] is True
    assert schemas.CategoriesSearchSchema().load({"category": "10113-000"})["category"] == "10113-000"
    with pytest.raises(ValidationError):
        schemas.CategoriesSearchSchema().load({})


def test_reviews_schema():
    loaded = schemas.CompanyReviewsSchema().load({"company": "1296-7039385"})
    assert loaded == {"company": "1296-7039385", "page": 1, "sort": "reviewDate desc, id desc"}
    assert schemas.CompanyReviewsSchema().load({"company": "1296-7039385", "sort": "lowest", "page": "469"})["sort"] \
        == "reviewStarRating asc"
    with pytest.raises(ValidationError):
        schemas.CompanyReviewsSchema().load({"company": "1296-7039385", "sort": "best"})
    with pytest.raises(ValidationError):
        schemas.CompanyReviewsSchema().load({"company": "1296-7039385", "page": "1001"})


def test_complaints_schema():
    loaded = schemas.CompanyComplaintsSchema().load({"company": "1296-7039385", "type": "Delivery", "status": "RESOLVED"})
    assert loaded == {"company": "1296-7039385", "page": 1, "type": "delivery", "status": "resolved"}
    assert schemas.CompanyComplaintsSchema().load({"company": "1296-7039385", "type": "billing"})["type"] == "billingissues"
    with pytest.raises(ValidationError) as e:
        schemas.CompanyComplaintsSchema().load({"company": "1296-7039385", "type": "refund"})
    assert "type" in e.value.messages
    with pytest.raises(ValidationError):
        schemas.CompanyComplaintsSchema().load({"company": "1296-7039385", "page": "1001"})


def test_autocomplete_schemas():
    assert schemas.CompaniesAutocompleteSchema().load({"query": "amaz", "location": "Seattle, WA"}) == \
        {"query": "amaz", "location": "Seattle, WA", "country": "USA"}
    assert schemas.CategoriesAutocompleteSchema().load({"query": "roof", "country": "ca"}) == \
        {"query": "roof", "country": "CAN"}
    assert schemas.LocationsAutocompleteSchema().load({"query": "chic", "include_postal_codes": "false"}) == \
        {"query": "chic", "country": "USA", "include_postal_codes": False}
    with pytest.raises(ValidationError):
        schemas.CompaniesAutocompleteSchema().load({})
    with pytest.raises(ValidationError):
        schemas.LocationsAutocompleteSchema().load({"query": "x" * 101})
