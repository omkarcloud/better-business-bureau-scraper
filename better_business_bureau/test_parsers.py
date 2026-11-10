"""Offline tests for the Better Business Bureau parsers.

    python -m pytest better_business_bureau/test_parsers.py -q

Fixtures are real www.bbb.org pages and JSON captured 2026-11-07
(better_business_bureau/fixtures/): search pages (Chicago plumbers page 1,
a filtered + sorted name search page 2, a nonsense term), a city category
page, four profiles (Amazon: accredited multi-location with alerts and
licences; M G Painting: not rated, licence; Sullivan Lane: hours, media,
obfuscated email; a Canadian business), review and complaint pages (full
and empty), the suggest JSONs, the site's 404 page and a Cloudflare
challenge page. No network.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from better_business_bureau import parsers as P  # noqa: E402

FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def fixture(name):
    with open(os.path.join(FX, name), encoding="utf-8") as f:
        return json.load(f) if name.endswith(".json") else f.read()


def state_of(name):
    state = P.preloaded_state(fixture(name))
    assert state is not None, name
    return state


@pytest.fixture(scope="module")
def amazon():
    html = fixture("profile_amazon.html")
    return P.parse_profile(P.preloaded_state(html), html)


@pytest.fixture(scope="module")
def sullivan():
    html = fixture("profile_sullivan_lane_email_hours.html")
    return P.parse_profile(P.preloaded_state(html), html)


@pytest.fixture(scope="module")
def painting():
    html = fixture("profile_mg_painting_not_rated.html")
    return P.parse_profile(P.preloaded_state(html), html, "1216-220091")


@pytest.fixture(scope="module")
def canada():
    html = fixture("profile_jackson_canada.html")
    return P.parse_profile(P.preloaded_state(html), html)


# ---- primitives -----------------------------------------------------------------

def test_preloaded_state_absent_on_error_pages():
    assert P.preloaded_state(fixture("profile_not_found.html")) is None
    assert P.preloaded_state(fixture("challenge_403.html")) is None
    assert P.preloaded_state("") is None and P.preloaded_state(None) is None
    assert P.page_title(fixture("profile_not_found.html")).startswith("Page not found")
    assert P.page_title(fixture("challenge_403.html")).startswith("Just a moment")


@pytest.mark.parametrize("value,expected", [
    ("2004-04-01T00:00:00", "2004-04-01"),
    ({"day": "03", "month": "11", "year": "2026"}, "2026-11-03"),
    ({"day": 3, "month": 1, "year": 2026}, "2026-01-03"),
    ("", None), (None, None), ({"day": "x"}, None), ("yesterday", None),
])
def test_iso_date(value, expected):
    assert P.iso_date(value) == expected


def test_strip_tags_and_html_text():
    assert P.strip_tags("<em>Amazon</em> Painting, LLC") == "Amazon Painting, LLC"
    assert P.strip_tags("Plain") == "Plain"
    assert P.html_text("a&nbsp;b<br/>c") == "a b c"
    assert P.html_text("") is None


def test_decode_cfemail():
    assert P.decode_cfemail("1f7a726a2d5f6a73736a69767e753b7e73706a7a71703d7c7072") != "Amon@SullivanLaneInc.com"
    html = fixture("profile_sullivan_lane_email_hours.html")
    assert P.page_emails(html) == ["Amon@SullivanLaneInc.com"]
    assert P.page_emails(fixture("profile_amazon.html")) == []
    assert P.page_emails(None) == []


# ---- search -------------------------------------------------------------------

def test_parse_search_page():
    result = P.parse_search(state_of("search_plumber_chicago_p1.html"), 1)
    assert result["query"] == "plumber"
    assert result["location"]["display_text"] == "Chicago, IL"
    assert result["location"]["latitude"] == 41.870171
    assert result["location"]["bbb_office"] == {"id": "0654", "name": "BBB of Chicago & Northern Illinois"}
    assert result["sort"] == "Relevance"
    assert result["pagination"] == {"page": 1, "items_per_page": 15, "total_pages": 15, "total_count": 4706}
    assert len(result["results"]) == 15
    assert result["filters"]["categories"][0] == {"id": "10113-000", "name": "Plumber"}
    assert result["filters"]["states"] == ["IA", "IL", "IN", "MI", "OH", "WI"]
    assert result["related_categories"][0] == {"name": "Plumber",
                                               "link": "https://www.bbb.org/us/il/chicago/category/plumber"}
    first = result["results"][0]
    assert first["id"] == "0654-88560011"
    assert first["name"] == "Sinks-N-Sumps Plumbing Service"
    assert first["link"] == "https://www.bbb.org/us/il/cicero/profile/plumber/sinks-n-sumps-plumbing-service-0654-88560011"
    assert first["rating"] == "A+" and first["rating_score"] == 100
    assert first["is_accredited"] is True and first["is_out_of_business"] is False
    assert first["primary_category"] == {"id": "10113-000", "name": "Plumber"}
    assert len(first["categories"]) == 4
    assert first["phone"] == "(312) 500-0911" and first["phones"] == ["(312) 500-0911"]
    assert first["address"] == {"street": "1409 S 50th Ct", "city": "Cicero", "state": "IL", "postal_code": "60804-1324"}
    assert first["location"] == {"latitude": 41.87, "longitude": -87.67}
    assert "Chicago, IL" in first["service_areas"]
    assert first["bbb_office"]["id"] == "0654"
    assert first["leave_review_link"].endswith("/leave-a-review")
    assert first["logo_link"] is None and first["distance_miles"] is None


def test_parse_search_strips_highlights_and_keeps_filters():
    result = P.parse_search(state_of("search_name_amazon_filtered.html"), 2)
    assert result["query"] == "Amazon"
    assert result["location"] is None
    assert result["sort"] == "Rating"
    assert result["pagination"]["page"] == 2
    assert all("<em>" not in r["name"] for r in result["results"])
    assert all(r["rating"] is None or r["rating"].startswith("A") for r in result["results"])
    assert "AB" in result["filters"]["states"]


def test_parse_search_fuzzy_no_match_is_a_normal_page():
    result = P.parse_search(state_of("search_no_results.html"), 1)
    assert result["pagination"]["total_count"] > 0
    assert len(result["results"]) == 15


def test_parse_category_page_shares_the_search_shape():
    result = P.parse_search(state_of("category_plumber_chicago.html"), 1)
    assert result["query"] == "Plumber"
    assert result["location"]["display_text"] == "Chicago, IL"
    assert result["pagination"]["total_count"] == 4602
    assert result["results"][0]["id"] == "0654-88560011"


def test_parse_search_empty_state():
    result = P.parse_search({}, 3)
    assert result["results"] == [] and result["pagination"] == {"page": 3, "items_per_page": 15,
                                                                 "total_pages": 0, "total_count": 0}
    assert P.parse_search(None, 1)["location"] is None


# ---- profile ----------------------------------------------------------------------

def test_profile_identity_and_rating(amazon):
    assert amazon["id"] == "1296-7039385"
    assert amazon["bbb_id"] == "1296" and amazon["business_id"] == "7039385"
    assert amazon["name"] == "Amazon.com"
    assert "Amazon Prime" in amazon["alternate_names"]
    assert amazon["link"] == "https://www.bbb.org/us/wa/seattle/profile/ecommerce/amazoncom-1296-7039385"
    assert amazon["rating"] == {"grade": "A+", "is_rated": True, "not_rated_reason": None,
                                "reasons": ["Customer Reviews are not used in the calculation of the BBB Letter Grade Rating."]}
    assert amazon["accreditation"]["is_accredited"] is True
    assert amazon["accreditation"]["since"] == "1996-08-01"
    assert amazon["is_multi_location"] is True and amazon["is_headquarters"] is True
    assert amazon["accepts_quote_requests"] is True


def test_profile_business_facts(amazon):
    assert amazon["description"] == "Amazon.com offers new and used items for sale through the Internet."
    assert amazon["products_and_services"].startswith("Internet Online Shopping")
    assert amazon["refund_and_exchange_policy"].startswith("You may return most new")
    assert amazon["entity_type"] == "Corporation"
    assert amazon["years_in_business"] == 31
    assert amazon["number_of_employees"] == 1300000
    assert amazon["payment_methods"] == ["Discover"]
    assert amazon["dates"] == {"business_started": "1995-07-01", "local_business_started": "2005-10-24",
                               "incorporated": "1996-05-28", "new_owner": None, "bbb_file_opened": "1996-08-01",
                               "accredited": "1996-08-01"}
    assert amazon["categories"]["primary"] == {"id": "65974-000", "name": "Ecommerce"}
    assert amazon["categories"]["items"][0] == {"name": "Ecommerce",
                                                "link": "https://www.bbb.org/us/wa/seattle/category/ecommerce"}


def test_profile_contact_and_people(amazon):
    contact = amazon["contact"]
    assert contact["phone"] == "(888) 280-4331"
    assert {"value": "(866) 216-1074", "label": "Other Phone"} in contact["additional_phones"]
    assert contact["fax_numbers"] == [{"value": "(206) 266-1838", "label": "Primary Fax"}]
    assert contact["email"] is None and contact["additional_emails"] == []
    assert "https://www.amazon.com/contact" in contact["websites"]
    assert amazon["people"][0] == {"name": "Mr. Jeff Bezos", "title": "Founder", "position": None, "is_principal": True,
                                   "is_management": True, "is_primary_contact": False, "is_customer_contact": False}
    assert amazon["address"] == {"street": "202 Westlake Ave N Ste 2", "street_2": None, "city": "Seattle",
                                 "state": "WA", "postal_code": "98109-5264"}
    assert amazon["location"]["latitude"] == 47.620049 and amazon["location"]["is_us_based"] is True
    assert amazon["location"]["serving_area"] == "Amazon.com serves Nationwide."
    assert "WA" in amazon["location"]["serving_areas"][0]["states"]
    assert amazon["location"]["serving_areas"][0]["countries"] == ["USA"]


def test_profile_alerts_licenses_social_locations(amazon):
    assert len(amazon["alerts"]) == 4
    alert = amazon["alerts"][0]
    assert alert["type_id"] == 8103 and alert["severity"] == 1 and alert["is_on_overview"] is True
    assert alert["title"].startswith("Government Action")
    assert "Federal Trade Commission" in alert["text"] and "<" not in alert["text"]
    assert "<strong>" in alert["html"]
    assert amazon["licenses"]["items"][0]["number"] == "601720490"
    assert amazon["licenses"]["items"][0]["agency"]["name"] == "Washington Secretary of State"
    assert {"type": "facebook", "label": "Facebook", "link": "https://www.facebook.com/Amazon"} in amazon["social_media"]
    assert amazon["locations"]["count"] == 20
    assert len(amazon["locations"]["items"]) == 5
    hq = amazon["locations"]["items"][0]
    assert hq["id"] == "1296-7039385" and hq["is_headquarters"] is True and hq["address"]["city"] == "Seattle"
    assert amazon["reviews_summary"]["count"] == 4687 and amazon["reviews_summary"]["average_rating"] == 1.1
    assert amazon["reviews_summary"]["latest"][0]["author"] == "Jeffrey G"
    assert amazon["complaints_summary"] == {"count": 10000, "closed_last_3_years": 61366, "closed_last_12_months": 17663}
    assert amazon["bbb_office"] == {"name": "BBB Great West + Pacific", "link": "https://www.bbb.org/local-bbb/bbb-great-west-pacific"}
    assert amazon["links"]["complaints"].endswith("/complaints")
    assert amazon["links"]["file_complaint"] == "https://www.bbb.org/file-a-complaint/1296-7039385"
    assert {t["title"] for t in amazon["additional_information"]} == {
        "Refund and Exchange Policy", "Products and Services", "Rating Reason", "Pending Government Action"}


def test_profile_hours_media_email(sullivan):
    assert sullivan["id"] == "0654-1000012025"
    assert sullivan["contact"]["email"] == "Amon@SullivanLaneInc.com"
    assert sullivan["contact"]["additional_emails"] == []
    assert "&nbsp;" not in sullivan["description"] and "<br" not in sullivan["description"]
    assert sullivan["hours"]["monday"] == {"periods": [{"open": "09:00", "close": "17:00"}], "is_closed": False, "note": None}
    assert sullivan["hours"]["saturday"] == {"periods": [], "is_closed": True, "note": "Closed"}
    assert sullivan["media"]["logo_link"].startswith("https://m.bbb.org/prod/ProfileImages/")
    assert len(sullivan["media"]["images"]) == 3
    assert sullivan["media"]["images"][0]["caption"] == "Kitchen Remodeling"
    assert sullivan["referral_assistance"][0].startswith("Illinois Department of Financial")
    assert sullivan["people"][0]["name"] == "Mr. Amon Nickerson"
    assert sullivan["number_of_employees"] is None


def test_profile_not_rated_sparse(painting):
    assert painting["id"] == "1216-220091"
    assert painting["name"] == "M G Painting"
    assert painting["rating"]["grade"] == "NR" and painting["rating"]["is_rated"] is False
    assert painting["rating"]["not_rated_reason"].startswith("BBB does not have sufficient information")
    assert painting["accreditation"]["is_accredited"] is False
    assert painting["entity_type"] == "Sole Proprietorship"
    assert painting["licenses"]["items"][0] == {
        "number": "796236", "expiration_date": "2027-06-30", "notes": None,
        "agency": {"name": "2-Contractors State Licensing Board", "phone": "800-3212752", "email": None,
                   "link": "https://www.cslb.ca.gov/", "address": "100 Paseo De San Antonio #319 San Jose CA 95113"}}
    assert painting["hours"] is None and painting["description"] is None
    assert painting["reviews_summary"] == {"count": 0, "average_rating": None, "are_suppressed": False, "latest": []}
    assert painting["complaints_summary"]["count"] == 0
    assert painting["social_media"] == [] and painting["alerts"] == []
    assert painting["faq"][0]["question"] == "Is M G Painting BBB Accredited?"
    assert painting["locations"]["count"] == 1


def test_profile_canada(canada):
    assert canada["id"] == "0107-1131634"
    assert canada["link"].startswith("https://www.bbb.org/ca/on/east-york/profile/")
    assert canada["address"]["state"] == "ON" and canada["address"]["postal_code"] == "M4G 1Y9"
    assert canada["location"]["is_us_based"] is False
    assert {"city": "Ajax", "state": "ON"} in canada["location"]["serving_areas"][0]["cities"]
    assert canada["location"]["serving_areas"][0]["counties"] == [{"county": "Toronto", "state": "ON"}]
    assert canada["contact"]["fax_numbers"] == [{"value": "(416) 778-6289", "label": "Primary Fax"}]
    assert canada["bbb_office"]["name"] == "BBB Serving Central Ontario"


def test_profile_empty_state_never_crashes():
    record = P.parse_profile({}, None, "1-2")
    assert record["id"] == "1-2" and record["name"] is None
    assert record["contact"]["email"] is None and record["people"] == [] and record["hours"] is None
    assert record["locations"] == {"count": None, "items": []}
    assert P.parse_profile(None, "", None)["id"] is None


# ---- reviews -------------------------------------------------------------------------

def test_parse_reviews_page():
    result = P.parse_reviews(state_of("reviews_amazon_p2.html"), 2)
    assert result["sort"] == "reviewDate desc, id desc"
    assert result["pagination"] == {"page": 2, "items_per_page": 10, "total_pages": 469, "total_count": 4687}
    assert len(result["reviews"]) == 10
    first = result["reviews"][0]
    assert first["id"] == "1296_7039385_892674"
    assert first["author"] == "Gina O" and first["rating"] == 1 and first["date"] == "2026-10-31"
    assert first["text"].startswith("My shipment that was supposed to arrive")
    assert first["business_response"] is None and first["customer_response"] is None


def test_parse_reviews_empty():
    result = P.parse_reviews(state_of("reviews_mg_painting_empty.html"), 1)
    assert result["reviews"] == []
    assert result["pagination"] == {"page": 1, "items_per_page": 10, "total_pages": 0, "total_count": 0}
    assert P.parse_reviews({}, 1)["reviews"] == []


def test_parse_review_with_responses():
    review = P.parse_review({"id": "x", "displayName": "A", "reviewStarRating": 5, "text": "Great",
                             "date": {"day": "01", "month": "02", "year": "2026"},
                             "businessResponseText": "Thanks <b>a lot</b>", "businessResponseDate": "2026-02-02T00:00:00",
                             "extendedText": ["more"]})
    assert review["text"] == "Great more"
    assert review["business_response"] == {"text": "Thanks a lot", "date": "2026-02-02"}
    assert review["date"] == "2026-02-01"


# ---- complaints ----------------------------------------------------------------------

def test_parse_complaints_page():
    result = P.parse_complaints(state_of("complaints_amazon_delivery_resolved_p2.html"), 2)
    assert result["hidden_count"] == 1085
    assert result["filters"]["types"][0] == {"id": "productissues", "count": 26563}
    assert result["filters"]["statuses"] == [{"id": "answered", "count": 49143}, {"id": "resolved", "count": 12235}]
    assert result["pagination"] == {"page": 2, "items_per_page": 10, "has_next": True, "total_pages": 188,
                                    "total_count": 1875}
    assert len(result["complaints"]) == 10
    first = result["complaints"][0]
    assert first["id"] == "1296_7039385_25411670"
    assert first["type"] == "Delivery Issues" and first["status"] == "Resolved" and first["date"] == "2026-10-20"
    assert first["text"].startswith("Good afternoon")
    assert all(c["type"] == "Delivery Issues" and c["status"] == "Resolved" for c in result["complaints"])
    with_responses = [c for c in result["complaints"] if c["responses"]]
    assert with_responses and with_responses[0]["responses"][0]["from"] in ("consumer", "business")


def test_parse_complaints_empty_and_past_the_end():
    result = P.parse_complaints(state_of("complaints_mg_painting_empty.html"), 1)
    assert result["complaints"] == [] and result["pagination"]["has_next"] is False
    assert result["pagination"]["total_count"] == 0 and result["pagination"]["total_pages"] == 0
    past = P.parse_complaints({"businessProfile": {"customerComplaints": {"items": [], "numFound": -1}}}, 1001)
    assert past["pagination"] == {"page": 1001, "items_per_page": 10, "has_next": False, "total_pages": None,
                                  "total_count": None}


def test_parse_complaints_caps_pages_at_the_site_limit():
    state = {"businessProfile": {"customerComplaints": {"items": [{"id": str(i)} for i in range(10)], "numFound": 10000}}}
    assert P.parse_complaints(state, 1)["pagination"]["total_pages"] == 1000
    assert P.parse_complaints(state, 1000)["pagination"]["has_next"] is False


# ---- suggest -----------------------------------------------------------------------------

def test_parse_suggest_find_mixed():
    result = P.parse_suggest_find(fixture("suggest_find_plumb.json"))
    assert len(result["businesses"]) == 5 and len(result["categories"]) == 5
    business = result["businesses"][0]
    assert business["id"] == "1296-59001706" and business["name"] == "Planet Plumbing & Drain"
    assert business["link"].startswith("https://www.bbb.org/us/co/boulder/profile/")
    assert business["is_accredited"] is True and business["is_headquarters"] is True
    category = result["categories"][0]
    assert category == {"id": "10113-300", "name": "highly rated plumbing renovation", "slug": "plumbing-renovation",
                        "link": "https://www.bbb.org/us/category/plumbing-renovation", "tags": ["highly rated"]}
    only = P.parse_suggest_find(fixture("suggest_find_plumb.json"), "Category")
    assert only["businesses"] == [] and len(only["categories"]) == 5


def test_parse_suggest_find_organizations_and_categories():
    orgs = P.parse_suggest_find(fixture("suggest_find_organization_amazon_seattle.json"), "Organization")["businesses"]
    assert len(orgs) == 10 and orgs[0]["name"] == "Little Amazon" and orgs[0]["is_accredited"] is False
    cats = P.parse_suggest_find(fixture("suggest_find_category_roof_can.json"), "Category")["categories"]
    assert cats[0]["id"] == "21179-000" and cats[0]["name"] == "Roof Replacement" and "primary" in cats[0]["tags"]
    assert P.parse_suggest_find(None) == {"businesses": [], "categories": []}


def test_parse_suggest_location():
    result = P.parse_suggest_location(fixture("suggest_location_chic.json"))
    assert result[0] == {"id": "Chicago_IL_USA", "display_text": "Chicago, IL", "city": "Chicago", "state": "IL",
                         "postal_code": None, "country": "USA", "latitude": 41.870171, "longitude": -87.671737,
                         "bbb_office_id": "0654"}
    postal = P.parse_suggest_location([{"id": "60654_USA", "displayText": "60654", "country": "USA",
                                        "latLng": "41.879503,-87.671", "bbbId": "0654"}])[0]
    assert postal["postal_code"] == "60654" and postal["city"] is None and postal["state"] is None
    assert P.parse_suggest_location(fixture("suggest_location_none.json")) == []
    assert P.parse_suggest_location({"bad": 1}) == []
