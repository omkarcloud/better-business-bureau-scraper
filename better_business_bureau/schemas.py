"""Marshmallow request schemas for every /better-business-bureau/* route.

ONE param per input (tripadvisor QueryOrIdField convention, never a sibling
`url`/`id` pair), resolved by better_business_bureau/refs.py:

    company    a BBB business id "<bbbId>-<businessId>" (1296-7039385, the
               two numbers at the end of a profile link) OR any www.bbb.org
               profile link, any tab of it
    category   a BBB category code (10113-000), a category slug (plumber)
               OR a www.bbb.org category link

Vocabularies are the site's own query tokens (researched 2026-11-07):
sort = Relevance | Distance | Rating | AToZ | ZToA, rating filter = one
letter grade (A covers A+ / A / A-), distance = 5 | 10 | 25 | 50 | 100
miles, country = USA | CAN, complaint type / status slugs as the site's
own filter form uses them.
"""
from marshmallow import ValidationError, validates_schema

from schema_fields import BaseSchema, ChoiceField, Flag, PageField, QueryField, RefField, StrippedString
from better_business_bureau import refs
from better_business_bureau.parsers import COMPLAINTS_MAX_PAGE, SEARCH_MAX_PAGES

# Reviews: 10 per page and the site publishes the total; Amazon has 469 pages.
MAX_REVIEW_PAGE = 1000

SORTS = {"relevance": "Relevance", "distance": "Distance", "rating": "Rating",
         "name_asc": "AToZ", "name_desc": "ZToA"}
RATINGS = {"A": "A", "B": "B", "C": "C", "D": "D", "F": "F"}
DISTANCES = {"5": "5", "10": "10", "25": "25", "50": "50", "100": "100"}
SEARCH_TYPES = {"name": "Name", "category": "Category"}
REVIEW_SORTS = {"newest": "reviewDate desc, id desc", "oldest": "reviewDate asc",
                "highest": "reviewStarRating desc", "lowest": "reviewStarRating asc"}
COMPLAINT_TYPES = {"product_issues": "productissues", "service_or_repair": "serviceorrepair",
                   "delivery": "delivery", "billing": "billingissues",
                   "customer_service": "customerservice", "sales_advertising": "salesadvertising",
                   "order": "order"}
COMPLAINT_STATUSES = {"answered": "answered", "resolved": "resolved"}

_COMPANY = {"description": "BBB business id (1296-7039385: the two numbers at the end of the profile "
                           "link) or a www.bbb.org profile link"}
_COUNTRY = {"description": "country of the BBB directory: us (default) or ca"}
_LOCATION = {"description": "city and state (\"Chicago, IL\"), a state, a ZIP / postal code; "
                            "empty = the whole country"}
_PAGE = {"description": "result page (15 results per page, the site serves at most 15 pages)"}
_SORT = {"description": "relevance (default), distance (needs location), rating, name_asc, name_desc"}
_RATING = {"description": "minimum BBB letter grade family: A (A+ / A / A-), B, C, D or F"}
_STATE = {"description": "two-letter state / province code to keep (IL, ON)"}
_DISTANCE = {"description": "miles around the location: 5, 10, 25, 50 or 100"}
_ACCREDITED = {"description": "true = BBB Accredited businesses only"}
_QUOTE = {"description": "true = only businesses that take quote requests through BBB"}
_SERVING = {"description": "true = only businesses that list the searched location in their service area"}


class CompanyRefField(RefField):
    resolver = staticmethod(refs.resolve_company)


class CategoryRefField(RefField):
    resolver = staticmethod(refs.resolve_category)


class _SearchFilters(BaseSchema):
    """The filters every listing endpoint shares."""
    location = StrippedString(required=False, load_default=None, metadata=_LOCATION)
    country = ChoiceField(refs.COUNTRIES, load_default=refs.DEFAULT_COUNTRY, metadata=_COUNTRY)
    page = PageField(max_page=SEARCH_MAX_PAGES, metadata=_PAGE)
    sort = ChoiceField(SORTS, load_default="Relevance", metadata=_SORT)
    rating = ChoiceField(RATINGS, metadata=_RATING)
    state = StrippedString(required=False, load_default=None, metadata=_STATE)
    distance = ChoiceField(DISTANCES, metadata=_DISTANCE)
    accredited_only = Flag(load_default=False, metadata=_ACCREDITED)
    quote_requests_only = Flag(load_default=False, metadata=_QUOTE)
    serving_area_only = Flag(load_default=False, metadata=_SERVING)

    @validates_schema
    def _state_shape(self, data, **kwargs):
        state = data.get("state")
        if state is not None:
            if not (len(state) == 2 and state.isalpha()):
                raise ValidationError("Must be a two-letter state / province code (IL, ON).", "state")
            data["state"] = state.upper()
        if data.get("sort") == "Distance" and not data.get("location"):
            raise ValidationError("sort=distance needs a location.", "sort")
        if data.get("distance") and not data.get("location"):
            raise ValidationError("distance needs a location.", "distance")


class CompaniesSearchSchema(_SearchFilters):
    query = QueryField(metadata={"description": "business name, keyword or category to search for"})
    search_type = ChoiceField(SEARCH_TYPES, metadata={
        "description": "how the query is read: name (business names) or category; empty = both"})
    category = StrippedString(required=False, load_default=None, metadata={
        "description": "keep one BBB category by code (10113-000, from the response's filters.categories)"})

    @validates_schema
    def _category_code(self, data, **kwargs):
        code = data.get("category")
        if code is not None and not refs.is_category_code(code):
            raise ValidationError("Must be a BBB category code like 10113-000.", "category")


class CategoriesSearchSchema(_SearchFilters):
    category = CategoryRefField(metadata={
        "description": "BBB category code (10113-000), category slug (plumber) or a www.bbb.org category link"})


class CompanySchema(BaseSchema):
    company = CompanyRefField(metadata=_COMPANY)


class CompanyReviewsSchema(BaseSchema):
    company = CompanyRefField(metadata=_COMPANY)
    page = PageField(max_page=MAX_REVIEW_PAGE, metadata={"description": "review page (10 reviews per page)"})
    sort = ChoiceField(REVIEW_SORTS, load_default=REVIEW_SORTS["newest"], metadata={
        "description": "newest (default), oldest, highest or lowest star rating"})


class CompanyComplaintsSchema(BaseSchema):
    company = CompanyRefField(metadata=_COMPANY)
    page = PageField(max_page=COMPLAINTS_MAX_PAGE, metadata={
        "description": "complaint page (10 complaints per page, the site serves up to 1000 pages)"})
    type = ChoiceField(COMPLAINT_TYPES, metadata={
        "description": "complaint type: product_issues, service_or_repair, delivery, billing, "
                       "customer_service, sales_advertising or order"})
    status = ChoiceField(COMPLAINT_STATUSES, metadata={"description": "complaint status: answered or resolved"})


class CompaniesAutocompleteSchema(BaseSchema):
    query = QueryField(max_length=100, metadata={"description": "start of a business name"})
    location = StrippedString(required=False, load_default=None, metadata={
        "description": "city and state to rank nearby businesses first (\"Seattle, WA\")"})
    country = ChoiceField(refs.COUNTRIES, load_default=refs.DEFAULT_COUNTRY, metadata=_COUNTRY)


class CategoriesAutocompleteSchema(BaseSchema):
    query = QueryField(max_length=100, metadata={"description": "start of a category name (plumb, roof)"})
    country = ChoiceField(refs.COUNTRIES, load_default=refs.DEFAULT_COUNTRY, metadata=_COUNTRY)


class LocationsAutocompleteSchema(BaseSchema):
    query = QueryField(max_length=100, metadata={"description": "start of a city, state or ZIP / postal code"})
    country = ChoiceField(refs.COUNTRIES, load_default=refs.DEFAULT_COUNTRY, metadata=_COUNTRY)
    include_postal_codes = Flag(load_default=True, metadata={"description": "false = cities and states only"})
