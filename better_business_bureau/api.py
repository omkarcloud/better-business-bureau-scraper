"""The /better-business-bureau/* endpoint functions (route_glue's route_table
calls them with the schema's loaded kwargs).

Caching (cache.cached_call, TTLs in cache_config): companies/details caches
the parsed profile page under better_business_bureau.company keyed on the
business id; the canonical profile path of an id (one redirect hop) is
cached on its own under better_business_bureau.profile_path so the reviews
and complaints endpoints never pay for the profile page itself. Every list
endpoint caches its own page.

Pagination: search pages carry the site's total and its 15-page cap
(route_glue.paginate stops where the site stops); review pages carry the
total; complaint pages set has_next because the site caps its total at
10,000 and answers pages up to 1000.
"""
from cache import cached_call
from better_business_bureau import cache_config as ttl
from better_business_bureau import fetch, parsers, refs
from better_business_bureau.fetch import BBBBadRequest, BBBNotFound


# ---- search ------------------------------------------------------------------

_COUNTRY_NAMES = {"USA": "the United States", "CAN": "Canada"}


def _searched_page(params):
    """GET a search page; a location BBB cannot place in the searched country
    -> 400, instead of BBB's whole-index fallback (parsers.is_unplaced_search)."""
    state, html = fetch.fetch_search(params)
    if parsers.is_unplaced_search(state):
        country = params["find_country"]
        other = "ca" if country == "USA" else "us"
        raise BBBBadRequest(
            f"BBB cannot find the location {params.get('find_loc')!r} in {_COUNTRY_NAMES.get(country, country)}. "
            f"Check the spelling, or set country={other} for a location in {_COUNTRY_NAMES['CAN' if other == 'ca' else 'USA']}.")
    return state, html

def _search_params(data, find_text, find_type=None, find_entity=None):
    params = {"find_text": find_text, "find_country": data.get("country") or refs.DEFAULT_COUNTRY,
              "page": data.get("page") or 1}
    if data.get("location"):
        params["find_loc"] = data["location"]
    if find_type:
        params["find_type"] = find_type
    if find_entity:
        params["find_entity"] = find_entity
    sort = data.get("sort")
    if sort and sort != "Relevance":
        params["sort"] = sort
    if data.get("rating"):
        params["filter_ratings"] = data["rating"]
    if data.get("state"):
        params["filter_state"] = data["state"]
    if data.get("distance"):
        params["filter_distance"] = data["distance"]
    if data.get("category") and refs.is_category_code(data["category"]):
        params["filter_category"] = data["category"]
    # the site reads these three only as "1" ("true" is silently ignored)
    if data.get("accredited_only"):
        params["filter_accredited"] = "1"
    if data.get("quote_requests_only"):
        params["filter_raq"] = "1"
    if data.get("serving_area_only"):
        params["filter_sa"] = "1"
    return params


def _companies_search(**data):
    params = _search_params(data, data["query"], find_type=data.get("search_type"))
    state, _ = _searched_page(params)
    result = parsers.parse_search(state, data.get("page") or 1)
    result["query"] = data["query"]
    result["country"] = params["find_country"]
    return result


def companies_search(**data):
    """Search BBB business profiles by name, keyword or category near a city,
    state or ZIP, with BBB's own filters (letter grade, accredited only,
    distance, state, category, quote requests, service area) and sorts.
    15 results per page, 15 pages at most (the site's own cap)."""
    return cached_call("better_business_bureau.search", data, _companies_search, ttl.SEARCH_CACHE)


# ---- categories ----------------------------------------------------------------

def _category_by_code(code, country):
    """The category's name + slug for a code, through the suggest API."""
    payload = fetch.fetch_suggest_find(code, country, ["Category"])
    for item in parsers.parse_suggest_find(payload, "Category")["categories"]:
        if item.get("id") == code:
            return item
    return {"id": code, "name": None, "slug": None, "link": None, "tags": []}


def _category_by_slug(slug, country):
    """A category slug -> {id (code), name, slug}: the suggest API keyed on
    the slug's words, matched on the slug it returns. Unknown -> NotFound."""
    words = slug.replace("-", " ")
    payload = fetch.fetch_suggest_find(words, country, ["Category"])
    items = parsers.parse_suggest_find(payload, "Category")["categories"]
    exact = [i for i in items if i.get("slug") == slug]
    if not exact:
        named = [i for i in items if (i.get("name") or "").lower() == words.lower()]
        exact = named
    if not exact:
        raise BBBNotFound(f"category {slug!r} not found")
    primary = [i for i in exact if "primary" in (i.get("tags") or [])]
    return (primary or exact)[0]


def _resolve_category(category, country):
    if refs.is_category_code(category):
        return _category_by_code(category, country)
    return _category_by_slug(category, country)


def resolve_category(category, country):
    return cached_call("better_business_bureau.category", {"category": category, "country": country},
                       _resolve_category, ttl.CATEGORY_CODE_CACHE)


def _categories_search(**data):
    country = data.get("country") or refs.DEFAULT_COUNTRY
    category = resolve_category(data["category"], country)
    params = _search_params(data, category.get("name") or category["id"],
                           find_type="Category", find_entity=category["id"])
    state, _ = _searched_page(params)
    result = parsers.parse_search(state, data.get("page") or 1)
    name = category.get("name")
    if not name:
        # a code the suggest API does not echo: the page's own category
        # filter lists the searched category first, with its label
        name = next((c["name"] for c in result["filters"]["categories"] if c["id"] == category["id"]), None)
    result["query"] = name or result["query"]
    result["category"] = {"id": category["id"], "name": name, "slug": category.get("slug"),
                          "link": category.get("link")}
    result["country"] = country
    return result


def categories_search(**data):
    """Every business in one BBB category (a category code, slug or category
    link) across the country or near a location, with the same filters,
    sorts and paging as companies/search."""
    return cached_call("better_business_bureau.category_search", data, _categories_search, ttl.SEARCH_CACHE)


# ---- the shared company record -----------------------------------------------

def _profile_path(company):
    """The canonical profile path of a business id (cached; one redirect hop
    the first time). Seeds the process hint so fetch.* skip the hop."""
    path = cached_call("better_business_bureau.profile_path", {"company": company},
                       lambda company: fetch.profile_path(company), ttl.PROFILE_PATH_CACHE)
    refs.remember_profile_path(company, path)
    return path


def _company_record(company):
    state, html = fetch.fetch_profile(company)
    return parsers.parse_profile(state, html, company)


def _record(company):
    record = cached_call("better_business_bureau.company", {"company": company}, _company_record,
                         ttl.COMPANY_CACHE)
    link = (record.get("links") or {}).get("profile") or ""
    if link.startswith(refs.SITE):
        refs.remember_profile_path(company, link[len(refs.SITE):])
    return record


def _identity(state, company):
    record = parsers.parse_profile(state, None, company)
    return {"id": record["id"], "name": record["name"], "link": record["link"],
            "rating": (record.get("rating") or {}).get("grade"),
            "is_accredited": (record.get("accreditation") or {}).get("is_accredited")}


# ---- companies/details ---------------------------------------------------------

def company_details(company):
    """The whole public profile: identity, rating + reasons, accreditation,
    dates, contact (phone, decoded email, websites), principals, address +
    coordinates, hours, licences, social links, alerts (government actions),
    additional texts, review / complaint summaries, the first branches of a
    multi-location business, media and the site's own FAQ."""
    return _record(company)


# ---- companies/reviews ---------------------------------------------------------

def _company_reviews(company, page, sort):
    _profile_path(company)
    state, _ = fetch.fetch_reviews(company, page, sort)
    result = parsers.parse_reviews(state, page)
    return {"company": _identity(state, company), **result}


def company_reviews(**data):
    """A business's BBB customer reviews, 10 per page, newest first by default
    (or oldest, highest or lowest rated): star rating, full text, date,
    reviewer and any business response, with the total review count."""
    return cached_call("better_business_bureau.reviews", data, _company_reviews, ttl.REVIEWS_CACHE)


# ---- companies/complaints ------------------------------------------------------

def _company_complaints(company, page, type=None, status=None):
    _profile_path(company)
    state, _ = fetch.fetch_complaints(company, page, kind=type, status=status)
    result = parsers.parse_complaints(state, page)
    return {"company": _identity(state, company), "type": type, "status": status, **result}


def company_complaints(**data):
    """A business's BBB complaints, 10 per page, newest first, filterable by
    complaint type and status: complaint text, type, status, date and the
    response thread between customer and business, with per-type and
    per-status counts."""
    return cached_call("better_business_bureau.complaints", data, _company_complaints, ttl.COMPLAINTS_CACHE)


# ---- autocomplete ----------------------------------------------------------------

def _companies_autocomplete(query, country, location=None):
    payload = fetch.fetch_suggest_find(query, country, ["Organization"], location)
    results = parsers.parse_suggest_find(payload, "Organization")["businesses"]
    return {"query": query, "location": location, "country": country, "count": len(results), "results": results}


def companies_autocomplete(**data):
    """BBB's own business-name typeahead: matching businesses with id, profile
    link, address and accreditation, ranked around a location when given."""
    return cached_call("better_business_bureau.companies_autocomplete", data, _companies_autocomplete,
                       ttl.SUGGEST_CACHE)


def _categories_autocomplete(query, country):
    payload = fetch.fetch_suggest_find(query, country, ["Category"])
    results = parsers.parse_suggest_find(payload, "Category")["categories"]
    return {"query": query, "country": country, "count": len(results), "results": results}


def categories_autocomplete(**data):
    """BBB's own category typeahead: category code, name and slug for a
    partial category name."""
    return cached_call("better_business_bureau.categories_autocomplete", data, _categories_autocomplete,
                       ttl.SUGGEST_CACHE)


def _locations_autocomplete(query, country, include_postal_codes=True):
    payload = fetch.fetch_suggest_location(query, country, include_postal_codes)
    results = parsers.parse_suggest_location(payload)
    return {"query": query, "country": country, "count": len(results), "results": results}


def locations_autocomplete(**data):
    """BBB's own place typeahead: cities, states and ZIP / postal codes with
    coordinates and the local BBB that serves them."""
    return cached_call("better_business_bureau.locations_autocomplete", data, _locations_autocomplete,
                       ttl.SUGGEST_CACHE)
