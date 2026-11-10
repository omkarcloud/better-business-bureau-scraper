"""Reference resolvers + the small vocabularies the /better-business-bureau/*
schemas need.

ONE param per input (tripadvisor QueryOrIdField convention): `company`
accepts a bare BBB business id OR any www.bbb.org profile link (any tab of
it); `category` accepts a BBB category code, a category slug OR a category
link. Resolvers raise ValueError with a user-facing message (RefField turns
it into a 400).

Identifier shapes (bbb.org, researched 2026-11-07):
  * business id   "<bbbId>-<businessId>": the 4-digit local-bureau code and
                  the bureau's numeric business id, the tail of every profile
                  URL (/us/wa/seattle/profile/ecommerce/amazoncom-1296-7039385).
                  The site redirects any URL whose tail is a known id to the
                  canonical profile path as long as the state segment is a
                  real state code, so the id alone addresses a business
                  (fetch.profile_path()). Search results carry it as
                  bbbId + businessId, the suggest API as "<bbb>_<biz>_<addr>".
  * category code "<5 digits>-<3 digits>" (tobId: 10113-000 = Plumber),
                  with a URL slug per category (/us/category/plumber).
"""
import re
import threading
from urllib.parse import urlparse

SITE = "https://www.bbb.org"
SITE_HOST = "www.bbb.org"

ID_RE = re.compile(r"^(\d{4})[-_](\d{1,12})$")
CATEGORY_CODE_RE = re.compile(r"^\d{5}-\d{3}$")
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

# The id is the tail of the profile path's last segment, before any tab
# (/customer-reviews, /complaints, /details, /more-info, ...) or query.
_LINK_ID_RE = re.compile(r"/profile/[^/?#]+/[^/?#]*?(\d{4})-(\d{1,12})(?:/|\?|#|$)")
_LINK_CATEGORY_RE = re.compile(r"/category/([a-z0-9-]+)(?:/accredited)?(?:/|\?|#|$)", re.I)

# Country tokens the site's query strings use (find_country / the suggest API).
COUNTRIES = {"us": "USA", "ca": "CAN"}
DEFAULT_COUNTRY = "USA"


def _is_link(value):
    return value.startswith(("http://", "https://", "//"))


def _as_url(value):
    return value if not value.startswith("//") else "https:" + value


def _host_is_bbb(url):
    host = (urlparse(url).hostname or "").lower()
    return host == "bbb.org" or host.endswith(".bbb.org")


def company_id(bbb_id, business_id):
    """The public id for a (bbbId, businessId) pair: "1296-7039385"."""
    if bbb_id in (None, "") or business_id in (None, ""):
        return None
    return f"{bbb_id}-{business_id}"


def split_id(value):
    """"1296-7039385" -> ("1296", "7039385")."""
    match = ID_RE.match(value)
    return (match.group(1), match.group(2)) if match else (None, None)


def resolve_company(value):
    """Bare "<bbbId>-<businessId>" or any bbb.org profile link -> the id.
    A link's canonical path is remembered so the first fetch skips the
    redirect hop (remember_profile_path)."""
    value = (value or "").strip()
    match = ID_RE.match(value)
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    if _is_link(value):
        url = _as_url(value)
        if not _host_is_bbb(url):
            raise ValueError("Must be a www.bbb.org link.")
        match = _LINK_ID_RE.search(urlparse(url).path)
        if match:
            ident = f"{match.group(1)}-{match.group(2)}"
            path = urlparse(url).path
            remember_profile_path(ident, path[:path.index(match.group(0)) + len(match.group(0).rstrip("/?#"))])
            return ident
        raise ValueError("Must be a www.bbb.org business profile link "
                         "(https://www.bbb.org/us/<state>/<city>/profile/<category>/<name>-<bbbId>-<businessId>).")
    raise ValueError("Must be a BBB business id (1296-7039385: the two numbers at the end of the "
                     "profile link) or a www.bbb.org profile link.")


def resolve_category(value):
    """A category code (10113-000), a category slug (plumber) or a
    bbb.org category link -> the code or the slug (api.py resolves a slug to
    its code through the site's suggest API)."""
    value = (value or "").strip()
    if CATEGORY_CODE_RE.match(value):
        return value
    if _is_link(value):
        url = _as_url(value)
        if not _host_is_bbb(url):
            raise ValueError("Must be a www.bbb.org link.")
        match = _LINK_CATEGORY_RE.search(urlparse(url).path)
        if match:
            return match.group(1).lower()
        raise ValueError("Must be a www.bbb.org category link "
                         "(https://www.bbb.org/us/category/plumber or /us/<state>/<city>/category/<slug>).")
    slug = value.lower().replace(" ", "-")
    if SLUG_RE.match(slug):
        return slug
    raise ValueError("Must be a BBB category code (10113-000), a category slug (plumber) "
                     "or a www.bbb.org category link.")


def is_category_code(value):
    return bool(CATEGORY_CODE_RE.match(value or ""))


# ---- canonical profile paths ---------------------------------------------------
# Process-local hint: id -> canonical profile path ("/us/wa/seattle/profile/
# ecommerce/amazoncom-1296-7039385"), seeded by a link the caller passed or
# by the redirect the site answered. Saves the 301 hop on later calls in
# this process; the durable copy is the cached company record (api.py).
_paths = {}
_paths_lock = threading.Lock()


def remember_profile_path(ident, path):
    if ident and path and path.startswith("/"):
        with _paths_lock:
            _paths[ident] = path.rstrip("/")


def known_profile_path(ident):
    with _paths_lock:
        return _paths.get(ident)


def stub_profile_path(ident):
    """A path the site 301s to the canonical profile: the state segment must
    be a real state code (an unknown one is a 404), the city, category and
    name slugs may be anything (verified 2026-11-07)."""
    return f"/us/ca/city/profile/business/business-{ident}"


def absolute(path):
    """A site-relative path or an absolute URL -> absolute URL (None stays None)."""
    if not path:
        return None
    if path.startswith(("http://", "https://")):
        return path
    return SITE + (path if path.startswith("/") else "/" + path)
