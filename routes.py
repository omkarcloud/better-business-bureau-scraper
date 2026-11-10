"""The 8 Better Business Bureau endpoints. Every path is served with and
without the `/better-business-bureau` prefix, so code generated against the
hosted API on RapidAPI (paths like /companies/details) runs unchanged against
this server.

Each route validates the query with the module's marshmallow schema
(better_business_bureau/schemas.py: one param per input, so `company` takes a
BBB business id or any bbb.org profile link), calls the endpoint function
(better_business_bureau/api.py) and maps the module's failure taxonomy to HTTP
exactly like the hosted API: bad params -> 400, an unknown business or
category -> 404 with a plain message, a block or upstream failure -> 502,
anything else -> 500. Paged endpoints return the flat count / per_page /
current_page / total_pages / next / previous block with links to this server."""
import json
from urllib.parse import urlencode

from bottle import request, response, route

from better_business_bureau import api, schemas
from schema_fields import load_query
from scraper_errors import BadRequest, Blocked, NotFound, UpstreamError


def json_response(data, status=200):
    response.status = status
    response.content_type = "application/json"
    return json.dumps(data, ensure_ascii=False)


def query_dict():
    """The request query as unicode strings (bottle 0.12's .get() hands back
    latin-1 decoded bytes, so getunicode is mandatory)."""
    return {key: request.query.getunicode(key) for key in request.query.keys()}


def _as_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _page_link(path, params, page):
    if not page:
        return None
    query = {k: v for k, v in params.items() if v not in (None, "", False)}
    query["page"] = page
    scheme, host = request.urlparts.scheme, request.urlparts.netloc
    return f"{scheme}://{host}{path}?{urlencode(query, doseq=True)}"


def paginate(result, path, params):
    """Lift the `pagination` block into the flat shape the hosted API returns:
    count / per_page / current_page / total_pages / next / previous. A page
    that publishes no total (complaints past BBB's 10,000 cap) sets has_next
    instead, and total_pages stays as the site gave it."""
    pagination = result.pop("pagination", None) or {}
    result.pop("count", None)
    page = _as_int(pagination.get("page")) or _as_int(params.get("page")) or 1
    if "has_next" in pagination:
        has_next = bool(pagination["has_next"])
        total_pages = pagination.get("total_pages")
        if total_pages is not None:
            total_pages = _as_int(total_pages, None)
    else:
        total_pages = max(_as_int(pagination.get("total_pages")), 0)
        has_next = page < total_pages
    out = {
        "count": pagination.get("total_count"),
        "per_page": pagination.get("items_per_page"),
        "current_page": page,
        "total_pages": total_pages,
        "next": _page_link(path, params, page + 1 if has_next else None),
        "previous": _page_link(path, params, page - 1 if page > 1 else None),
    }
    out.update(result)
    return out


def call(label, schema_cls, impl, paginated=False):
    """Validate with the schema, run impl(**data), map errors to HTTP."""
    raw = query_dict()
    data, error = load_query(schema_cls, raw)
    if error:
        return json_response(error, 400)
    try:
        result = impl(**data)
    except ValueError as e:                 # bad id / params
        return json_response({"error": str(e)}, 400)
    except BadRequest as e:                 # upstream rejected the request
        return json_response({"error": f"better-business-bureau rejected the request: {e}"}, 400)
    except NotFound as e:
        return json_response({"error": str(e) or "not found"}, 404)
    except Blocked as e:
        return json_response({"error": f"better-business-bureau blocked the request, retry later: {e}"}, 502)
    except UpstreamError as e:
        return json_response({"error": f"better-business-bureau {label} failed: {e}"}, 502)
    except Exception as e:                  # parser surprises
        return json_response({"error": f"better-business-bureau {label} failed: {type(e).__name__}: {e}"}, 500)
    if paginated:
        result = paginate(result, request.path, raw)
    return json_response(result)


ENDPOINTS = [
    ("/companies/details", schemas.CompanySchema, api.company_details, False),
    ("/companies/reviews", schemas.CompanyReviewsSchema, api.company_reviews, True),
    ("/companies/complaints", schemas.CompanyComplaintsSchema, api.company_complaints, True),
    ("/companies/search", schemas.CompaniesSearchSchema, api.companies_search, True),
    ("/companies/autocomplete", schemas.CompaniesAutocompleteSchema, api.companies_autocomplete, False),
    ("/categories/search", schemas.CategoriesSearchSchema, api.categories_search, True),
    ("/categories/autocomplete", schemas.CategoriesAutocompleteSchema, api.categories_autocomplete, False),
    ("/locations/autocomplete", schemas.LocationsAutocompleteSchema, api.locations_autocomplete, False),
]


def mount(path, schema_cls, impl, paginated):
    """Serve an endpoint at /path and /better-business-bureau/path."""
    label = path.strip("/")

    def handler():
        return call(label, schema_cls, impl, paginated)
    handler.__name__ = "better_business_bureau_" + label.replace("/", "_").replace("-", "_")
    route(path, method="GET")(handler)
    route("/better-business-bureau" + path, method="GET")(handler)


for _path, _schema, _impl, _paginated in ENDPOINTS:
    mount(_path, _schema, _impl, _paginated)


@route("/", method="GET")
@route("/health", method="GET")
@route("/better-business-bureau/health", method="GET")
def health():
    return json_response({"status": "ok", "endpoints": [p for p, *_ in ENDPOINTS]})
