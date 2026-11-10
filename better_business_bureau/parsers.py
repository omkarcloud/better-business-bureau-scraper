"""HTML / JSON -> clean dicts for every /better-business-bureau/* endpoint.

Every bbb.org page embeds its data as one JSON object in
`window.__PRELOADED_STATE__ = {...};` (preloaded_state): the search and
category pages carry `searchResult`, a business profile `businessProfile`,
its /customer-reviews tab adds `businessProfile.customerReviews` and its
/complaints tab `businessProfile.customerComplaints`. Nothing here parses
rendered HTML except two things the state leaves out: the business email
(Cloudflare-obfuscated `data-cfemail` attribute, decode_cfemail) and the
page <title> (fetch.py uses it to tell a not-found page from a block). The
two typeahead calls (/api/suggest/find, /api/suggest/location) are plain
JSON lists.

Value conventions (shared with the other scraper packages):
  * keys     snake_case; `link` not `url`; booleans as questions
  * dates    ISO "2004-04-01" ("2004-04-01T00:00:00" and {day, month, year}
             both normalise); hours as "09:00"
  * absent   null, never "" / [] placeholders for scalars; the site's "" and
             0-for-unknown (numEmployees, averageOfReviewStarRatings when
             not displayed) are null here
  * text     search names come with <em> highlight tags around the matched
             words; they are stripped. Alert / policy texts are HTML and are
             returned both as plain `text` and as `html`.

Fixtures captured 2026-11-07 (better_business_bureau/fixtures/): a plumber
search in Chicago (page 1), a name search with rating filter + sort (page
2), a nonsense-term search (the site still returns fuzzy matches), a city
category page, three US profiles (Amazon: accredited, multi-location,
government-action alerts, 4.7K reviews / 10K complaints; M G Painting: not
rated, licence, no reviews; Sullivan Lane: hours, logo + image carousel,
obfuscated email, referral text), a Canadian profile, review pages
(Amazon page 2, an empty one), complaint pages (Amazon delivery + resolved
filter page 2, an empty one), the suggest JSONs, the site's 404 page and
a Cloudflare challenge page. Their inline <style> blocks were removed on
2026-11-10: nothing here reads CSS, and the site's login-form class names
tripped the secret grep the published open-source copy must pass.
"""
import fastjson
import math
import re

from bs4 import BeautifulSoup

from better_business_bureau.refs import SITE, absolute, company_id

SEARCH_PAGE_SIZE = 15     # the site's own page size; 15 pages at most (225 results)
SEARCH_MAX_PAGES = 15
REVIEWS_PAGE_SIZE = 10
COMPLAINTS_PAGE_SIZE = 10
COMPLAINTS_MAX_PAGE = 1000   # the site answers pages up to 1000, -1 results past it

_STATE_RE = re.compile(r"window\.__PRELOADED_STATE__\s*=\s*", re.S)
_TITLE_RE = re.compile(r"<title>([^<]*)</title>", re.I)
_TAG_RE = re.compile(r"<[^>]+>")
_CFEMAIL_RE = re.compile(r'data-cfemail="([0-9a-fA-F]+)"')
_MAILTO_RE = re.compile(r'href="mailto:([^"?]+)')
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_DAYS = {"m": "monday", "t": "tuesday", "w": "wednesday", "th": "thursday",
         "f": "friday", "sa": "saturday", "su": "sunday"}
_SOCIAL_TYPES = {"facebook": "facebook", "twitter": "twitter", "linkedin": "linkedin",
                 "instagram": "instagram", "youtube": "youtube", "pinterest": "pinterest",
                 "tiktok": "tiktok", "yelp": "yelp"}


# ---- primitives ----------------------------------------------------------------

def page_title(html):
    match = _TITLE_RE.search(html or "")
    return match.group(1).strip() if match else ""


def preloaded_state(html):
    """The page's `window.__PRELOADED_STATE__` object, or None when the page
    carries none (a 404 page, a challenge page)."""
    match = _STATE_RE.search(html or "")
    if not match:
        return None
    start = match.end()
    end = html.find("</script>", start)
    blob = html[start:end if end > 0 else None].strip().rstrip(";").strip()
    try:
        return fastjson.loads(blob)
    except Exception:
        # the blob may be JSON.parse("...") of an escaped string
        inner = re.match(r'JSON\.parse\((".*")\)\s*$', blob, re.S)
        if inner:
            try:
                return fastjson.loads(fastjson.loads(inner.group(1)))
            except Exception:
                return None
        return None


def clean(value):
    """Collapse whitespace; "" -> None. Non-strings pass through."""
    if value is None:
        return None
    if isinstance(value, str):
        value = " ".join(value.split())
        return value or None
    return value


def strip_tags(value):
    """"<em>Amazon</em> Painting" -> "Amazon Painting"; HTML entities decoded."""
    if value is None:
        return None
    if "<" not in value and "&" not in value:
        return clean(value)
    text = BeautifulSoup(value, "lxml").get_text(" ", strip=True)
    return clean(text)


def html_text(value):
    """An HTML fragment -> plain text with line breaks collapsed to spaces."""
    if not value:
        return None
    return clean(BeautifulSoup(value, "lxml").get_text(" ", strip=True))


def iso_date(value):
    """"2004-04-01T00:00:00" -> "2004-04-01"; {day, month, year} -> ISO;
    anything else -> None."""
    if not value:
        return None
    if isinstance(value, dict):
        try:
            return f"{int(value['year']):04d}-{int(value['month']):02d}-{int(value['day']):02d}"
        except (KeyError, TypeError, ValueError):
            return None
    if isinstance(value, str):
        match = re.match(r"(\d{4})-(\d{2})-(\d{2})", value)
        return match.group(0) if match else None
    return None


def iso_time(value):
    """"2026-09-05T09:00:00" -> "09:00"."""
    if not isinstance(value, str):
        return None
    match = re.search(r"T(\d{2}:\d{2})", value)
    return match.group(1) if match else None


def number(value):
    """int/float pass through (bool excluded); numeric strings parse; else None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        try:
            return float(value.replace(",", "")) if "." in value else int(value.replace(",", ""))
        except ValueError:
            return None
    return None


def positive(value):
    """The site writes 0 for "not stated" on counts like numEmployees."""
    value = number(value)
    return value if value else None


def decode_cfemail(encoded):
    """Cloudflare email obfuscation: hex string whose first byte XORs the rest."""
    try:
        key = int(encoded[:2], 16)
        return "".join(chr(int(encoded[i:i + 2], 16) ^ key) for i in range(2, len(encoded), 2))
    except (ValueError, IndexError):
        return None


def page_emails(html):
    """Every email the rendered profile shows (data-cfemail + mailto:),
    deduped in page order; the state's own emailAddress is empty even when
    the page shows one (2026-11-07)."""
    seen, out = set(), []
    for encoded in _CFEMAIL_RE.findall(html or ""):
        email = decode_cfemail(encoded)
        if email and _EMAIL_RE.match(email) and email.lower() not in seen:
            seen.add(email.lower())
            out.append(email)
    for email in _MAILTO_RE.findall(html or ""):
        if _EMAIL_RE.match(email) and email.lower() not in seen:
            seen.add(email.lower())
            out.append(email)
    # Cloudflare also obfuscates an email glued to the text before it inside
    # a free-text description ("(312) 772-5701Amon@x.com"): drop a candidate
    # that merely ends with another, shorter candidate.
    lowered = [e.lower() for e in out]
    return [e for e in out if not any(o != e.lower() and e.lower().endswith(o) for o in lowered)]


def _by_id_list(block):
    """{allIds, byId} -> the items in allIds order (tolerates either missing)."""
    if not isinstance(block, dict):
        return []
    by_id = block.get("byId") or {}
    ids = block.get("allIds")
    if isinstance(ids, list):
        return [by_id[i] for i in ids if i in by_id]
    return list(by_id.values())


def _link(url):
    return absolute(url) if url else None


# ---- search / category pages --------------------------------------------------

def _category(item):
    if not isinstance(item, dict):
        return None
    return {"id": clean(item.get("id")), "name": clean(item.get("name"))}


def parse_search_result(item):
    """One `searchResult.results[]` row -> a company card."""
    phones = [clean(p) for p in (item.get("phone") or []) if clean(p)]
    lat_lng = (item.get("location") or "").split(",")
    latitude = number(lat_lng[0]) if len(lat_lng) == 2 else None
    longitude = number(lat_lng[1]) if len(lat_lng) == 2 else None
    ident = company_id(item.get("bbbId"), item.get("businessId"))
    categories = [c for c in (_category(c) for c in (item.get("categories") or [])) if c]
    primary = {"id": clean(item.get("tobId")), "name": clean(item.get("tobText"))}
    return {
        "id": ident,
        "name": strip_tags(item.get("businessName")),
        "link": _link(item.get("reportUrl")),
        "rating": clean(item.get("rating")) or None,
        "rating_score": number(item.get("ratingScore")),
        "is_accredited": bool(item.get("bbbMember")),
        "accreditation_status": clean(item.get("accreditationStatus")),
        "is_out_of_business": bool(item.get("outOfBusinessStatus")),
        "out_of_business_status": clean(item.get("outOfBusinessStatus")),
        "is_charity": bool(item.get("isCharity")),
        "is_accredited_charity": bool(item.get("accreditedCharity")) if item.get("isCharity") else False,
        "has_charity_seal": bool(item.get("charitySeal")),
        "primary_category": primary if (primary["id"] or primary["name"]) else None,
        "categories": categories,
        "phones": phones,
        "phone": phones[0] if phones else None,
        "address": {
            "street": clean(item.get("address")),
            "city": clean(item.get("city")),
            "state": clean(item.get("state")),
            "postal_code": clean(item.get("postalcode")),
        },
        "location": {"latitude": latitude, "longitude": longitude},
        "distance_miles": number(item.get("distance")),
        "has_service_area": bool(item.get("hasServiceArea")),
        "service_area_description": clean(item.get("serviceAreaDescription")),
        "service_areas": [clean(a) for a in (item.get("serviceAreasSummary") or []) if clean(a)],
        "accepts_quote_requests": bool(item.get("raqEnabled")) and bool(item.get("requestAQuoteUrl")),
        "request_quote_link": _link(item.get("requestAQuoteUrl")),
        "leave_review_link": _link(item.get("leaveReviewUrl")),
        "logo_link": _link(item.get("logoUri")),
        "bbb_office": {"id": clean(item.get("bbbId")), "name": clean(item.get("bbbName"))},
        "relevance_score": number(item.get("score")),
    }


def _search_location(loc):
    if not isinstance(loc, dict) or not loc.get("id"):
        return None
    lat_lng = (loc.get("latLng") or "").split(",")
    bbb = loc.get("bbbInfo") or {}
    return {
        "id": clean(loc.get("id")),
        "display_text": clean(loc.get("displayText")),
        "city": clean(loc.get("city")),
        "state": clean(loc.get("state")),
        "state_name": clean(loc.get("stateFull")),
        "postal_code": clean(loc.get("postalCode")),
        "country": clean(loc.get("country")),
        "latitude": number(lat_lng[0]) if len(lat_lng) == 2 else None,
        "longitude": number(lat_lng[1]) if len(lat_lng) == 2 else None,
        "business_count": number(loc.get("businessCount")),
        "bbb_office": {"id": clean(bbb.get("bbbId") or bbb.get("id")), "name": clean(bbb.get("bbbName"))}
        if bbb.get("bbbName") else None,
    }


def _filter_options(filters, key):
    block = ((filters or {}).get("byId") or {}).get(key) or {}
    return [{"id": clean(o.get("value")), "name": clean(o.get("label"))}
            for o in (block.get("filterOptions") or []) if o.get("value")]


def _titled_links(items):
    return [{"name": clean(i.get("title")), "link": _link(i.get("url"))}
            for i in (items or []) if isinstance(i, dict) and i.get("title")]


def parse_search(state, page):
    """A search / category page state -> {results, filters, related
    categories, location, pagination}. The site serves at most 15 pages of
    15 whatever the total; `total_pages` is the site's own (capped) count so
    the next link stops where the site stops."""
    sr = (state or {}).get("searchResult") or {}
    results = [parse_search_result(r) for r in (sr.get("results") or []) if isinstance(r, dict)]
    total = number(sr.get("totalResults")) or 0
    total_pages = number(sr.get("totalPages")) or 0
    heading = sr.get("heading") or {}
    active_sort = next((s.get("value") for s in (sr.get("sortTypes") or []) if s.get("isActive")), None)
    return {
        "query": clean(heading.get("searchInputText")),
        "location": _search_location(sr.get("location")),
        "sort": clean(active_sort),
        "is_accredited_only": bool(sr.get("accredited")),
        "results": results,
        "filters": {
            "categories": _filter_options(sr.get("filters"), "filter_category"),
            "states": [o["id"] for o in _filter_options(sr.get("filters"), "filter_state")],
        },
        "related_categories": _titled_links(sr.get("relatedCategories")),
        "pagination": {
            "page": page,
            "items_per_page": SEARCH_PAGE_SIZE,
            "total_pages": min(int(total_pages), SEARCH_MAX_PAGES),
            "total_count": int(total),
        },
    }


# ---- business profile -----------------------------------------------------------

def _name(person):
    if not isinstance(person, dict):
        return None
    parts = [person.get("prefix"), person.get("first"), person.get("middle"), person.get("last"), person.get("suffix")]
    return clean(" ".join(p for p in parts if p)) or None


def _contacts(items):
    out = []
    for c in items or []:
        if not isinstance(c, dict):
            continue
        out.append({
            "name": _name(c.get("name")),
            "title": clean(c.get("title")),
            "position": clean(c.get("position")),
            "is_principal": bool(c.get("isPrincipal")),
            "is_management": bool(c.get("isManagement")),
            "is_primary_contact": bool(c.get("isPrimary")),
            "is_customer_contact": bool(c.get("isCustomer")),
        })
    return out


def _labelled(items):
    """additionalPhoneNumbers / additionalFaxNumbers / additionalEmailAddresses:
    [{name, value, labels: [{name, type}]}] -> [{value, label}]."""
    out = []
    for it in items or []:
        if isinstance(it, dict) and clean(it.get("value")):
            labels = [clean(l.get("name")) for l in (it.get("labels") or []) if isinstance(l, dict) and clean(l.get("name"))]
            out.append({"value": clean(it.get("value")), "label": labels[0] if labels else clean(it.get("name"))})
        elif isinstance(it, str) and clean(it):
            out.append({"value": clean(it), "label": None})
    return out


def _websites(items):
    out = []
    for it in items or []:
        value = it.get("value") if isinstance(it, dict) else it
        value = clean(value)
        if value and value not in out:
            out.append(value)
    return out


def _hours(block):
    """operatingHours {byId: {primary: {days: {byId: {m: {hours: [{openDate,
    closeDate}], note}}}}}} -> {monday: {periods, is_closed, note}, ...}."""
    if not isinstance(block, dict):
        return None
    schedules = block.get("byId") or {}
    primary = schedules.get("primary") or next(iter(schedules.values()), None)
    if not isinstance(primary, dict):
        return None
    days = (primary.get("days") or {}).get("byId") or {}
    out = {}
    for key, name in _DAYS.items():
        day = days.get(key)
        if not isinstance(day, dict):
            continue
        periods = [{"open": iso_time(h.get("openDate")), "close": iso_time(h.get("closeDate"))}
                   for h in (day.get("hours") or []) if isinstance(h, dict)]
        note = clean(day.get("note"))
        out[name] = {"periods": periods, "is_closed": not periods, "note": note}
    return out or None


def _licenses(block):
    if not isinstance(block, dict):
        return {"is_license_required": None, "items": [], "notes": []}
    items = []
    for d in block.get("details") or []:
        if not isinstance(d, dict):
            continue
        agency = d.get("licenseAgency") or {}
        items.append({
            "number": clean(d.get("licenseNumber")),
            "expiration_date": iso_date(d.get("expirationDate")),
            "notes": clean(d.get("notes")),
            "agency": {
                "name": clean(agency.get("name")),
                "phone": clean(agency.get("phoneNumber")),
                "email": clean(agency.get("email")),
                "link": clean(agency.get("url")),
                "address": clean(" ".join(str(agency.get(k) or "") for k in ("address", "city", "state", "zip"))),
            } if agency else None,
        })
    return {
        "is_license_required": bool(block.get("isCompetencyLicenseRequired")),
        "items": items,
        "notes": [html_text(t) for t in (block.get("licensingTexts") or []) if html_text(t)],
    }


def _alerts(block):
    out = []
    for a in _by_id_list(block):
        if not isinstance(a, dict):
            continue
        out.append({
            "type_id": number(a.get("alertTypeId")),
            "severity": number(a.get("severity")),
            "title": html_text(a.get("title")),
            "text": html_text(a.get("text")),
            "html": clean(a.get("text")),
            "is_on_overview": bool(a.get("isOverview")),
        })
    return out


def _texts(block):
    return [{"title": clean(t.get("title")), "text": html_text(t.get("text")), "html": clean(t.get("text"))}
            for t in _by_id_list(block) if isinstance(t, dict) and (t.get("title") or t.get("text"))]


def _text_by_title(texts, *titles):
    wanted = {t.lower() for t in titles}
    for t in texts:
        if (t.get("title") or "").lower() in wanted:
            return t.get("text")
    return None


def _media(block):
    block = block or {}
    logo = block.get("logo") or {}
    images, videos = [], []
    for item in _by_id_list(block.get("carouselItems")):
        if not isinstance(item, dict):
            continue
        entry = {"caption": clean(item.get("caption")) or clean(item.get("title")), "position": number(item.get("position"))}
        if item.get("isVideo") or item.get("videoUrl"):
            videos.append({**entry, "link": clean(item.get("videoUrl"))})
        elif item.get("imageUrl"):
            images.append({**entry, "link": clean(item.get("imageUrl"))})
    return {"logo_link": clean(logo.get("url")), "images": images, "videos": videos}


def _branch(loc):
    return {
        "id": company_id(loc.get("id", "").split("_")[0] if isinstance(loc.get("id"), str) else None, loc.get("businessId")),
        "name": clean(loc.get("name")),
        "link": _link(loc.get("url")),
        "phone": clean(loc.get("primaryPhone")),
        "address": {
            "street": clean(loc.get("address")),
            "city": clean(loc.get("city")),
            "state": clean(loc.get("stateProvince")),
            "postal_code": clean(loc.get("postalCode")),
            "country": clean(loc.get("country")),
        },
        "rating": clean(loc.get("rating")),
        "is_accredited": bool(loc.get("accredited")),
        "is_headquarters": bool(loc.get("isHQ")),
        "logo_link": _link(loc.get("logoUrl")),
    }


def _locations(block):
    """dialogLocations: the first five branches of a multi-location business
    plus the totals (the dialog's own paging is client-side and not served)."""
    block = block or {}
    results = block.get("results") or {}
    items = [_branch(l) for l in _by_id_list(results.get("locations")) if isinstance(l, dict)]
    return {
        "count": number(results.get("totalLocations")) if results.get("totalLocations") is not None else (len(items) or None),
        "items": items,
    }


def _social(items):
    out = []
    for s in items or []:
        if isinstance(s, dict) and clean(s.get("url")):
            kind = clean(s.get("type")) or clean(s.get("label"))
            out.append({"type": _SOCIAL_TYPES.get((kind or "").lower(), (kind or "").lower() or None),
                        "label": clean(s.get("label")), "link": clean(s.get("url"))})
    return out


def _serving_areas(items):
    """location.servingAreas: [{description, stateCodes, countryCodes,
    postalCodes, cityStates: [{city, stateCode}], countyStates: [{county,
    stateCode}]}] -> the same, in our names."""
    out = []
    for a in items or []:
        if isinstance(a, str):
            if clean(a):
                out.append({"description": clean(a), "states": [], "countries": [], "postal_codes": [],
                            "cities": [], "counties": []})
            continue
        if not isinstance(a, dict):
            continue
        out.append({
            "description": html_text(a.get("description")),
            "states": [clean(s) for s in (a.get("stateCodes") or []) if clean(s)],
            "countries": [clean(c) for c in (a.get("countryCodes") or []) if clean(c)],
            "postal_codes": [clean(p) for p in (a.get("postalCodes") or []) if clean(p)],
            "cities": [{"city": clean(c.get("city")), "state": clean(c.get("stateCode"))}
                       for c in (a.get("cityStates") or []) if isinstance(c, dict)],
            "counties": [{"county": clean(c.get("county")), "state": clean(c.get("stateCode"))}
                         for c in (a.get("countyStates") or []) if isinstance(c, dict)],
        })
    return out


def _address(block):
    if not isinstance(block, dict):
        return None
    return {
        "street": clean(block.get("addressLine1")),
        "street_2": clean(block.get("addressLine2")),
        "city": clean(block.get("city")),
        "state": clean(block.get("stateCode")),
        "postal_code": clean(block.get("zipCode")),
    }


def _faq(block):
    return [{"question": clean(f.get("question")), "answer": html_text(f.get("answer"))}
            for f in _by_id_list(block) if isinstance(f, dict) and f.get("question")]


def parse_profile(state, html=None, ident=None):
    """A profile page state (+ its HTML for the obfuscated email) -> the
    full company record. Every tab of the profile carries the same
    businessProfile block, so any tab's state parses here."""
    bp = (state or {}).get("businessProfile") or {}
    names = bp.get("names") or {}
    rating = bp.get("rating") or {}
    accreditation = bp.get("accreditationInformation") or {}
    dates = bp.get("dates") or {}
    categories = bp.get("categories") or {}
    contact = bp.get("contactInformation") or {}
    location = bp.get("location") or {}
    org = bp.get("orgDetails") or {}
    display = bp.get("display") or {}
    summary = bp.get("reviewsComplaintsSummary") or {}
    urls = bp.get("urls") or {}
    local = bp.get("localBbbData") or {}
    entity = org.get("typeOfEntity") or {}
    claim = display.get("claim") or {}
    texts = _texts(display.get("additionalInformationTexts"))
    emails = page_emails(html) if html else []
    state_email = clean(contact.get("emailAddress"))
    if state_email and state_email not in emails:
        emails.insert(0, state_email)
    extra_emails = [e["value"] for e in _labelled(contact.get("additionalEmailAddresses"))]
    for e in extra_emails:
        if e not in emails:
            emails.append(e)
    ident = ident or company_id(bp.get("bbbId"), bp.get("businessId"))
    profile_path = urls.get("profile")
    hq = org.get("hqInformation") or {}
    refund = org.get("refundExchangePolicy") or []
    products = html_text(display.get("prodSrvcsSummary")) or _text_by_title(texts, "Products and Services")
    average = summary.get("averageOfReviewStarRatings")
    return {
        "id": ident,
        "bbb_id": clean(bp.get("bbbId")),
        "business_id": clean(bp.get("businessId")),
        "name": clean(names.get("primary")),
        "alternate_names": [clean(n) for n in (names.get("altBusinessNames") or []) if clean(n)],
        "link": _link(profile_path),
        "rating": {
            "grade": clean(rating.get("bbbRating")),
            "is_rated": clean(rating.get("bbbRating")) not in (None, "NR"),
            "not_rated_reason": clean(rating.get("ratingReasonNotRated")),
            "reasons": [html_text(r) for r in (rating.get("ratingReasons") or []) if html_text(r)],
        },
        "accreditation": {
            "is_accredited": bool(accreditation.get("isAccredited")),
            "since": iso_date(dates.get("accredited")),
            "revoked_date": iso_date(dates.get("accreditationRevoked")),
            "notes": [html_text(t) for t in (accreditation.get("text") or []) if html_text(t)],
        },
        "is_out_of_business": bool(org.get("isOutOfBusiness")),
        "is_claimed": bool(claim.get("isClaimed")),
        "is_multi_location": bool(bp.get("isMultiLocation")),
        "is_headquarters": bool(location.get("isHq")),
        "is_local_report": bool(bp.get("isLocalReport")),
        "has_high_risk_category": bool(categories.get("hasHighRiskCategory")),
        "accepts_quote_requests": bool(display.get("isRequestQuoteActive")),
        "description": html_text(org.get("organizationDescription")),
        "products_and_services": products,
        "refund_and_exchange_policy": (
            clean(" ".join(html_text(r) or "" for r in refund)) if refund
            else _text_by_title(texts, "Refund and Exchange Policy")),
        "entity_type": clean(entity.get("name")) if entity.get("canDisplay", True) else None,
        "years_in_business": positive(org.get("yearsInBusiness")),
        "number_of_employees": positive(org.get("numEmployees")),
        "payment_methods": [clean(p) for p in (org.get("paymentMethods") or []) if clean(p)]
                           + [clean(p) for p in (org.get("paymentMethodCustomTexts") or []) if clean(p)],
        "dates": {
            "business_started": iso_date(dates.get("businessStart")),
            "local_business_started": iso_date(dates.get("businessLocalStart")),
            "incorporated": iso_date(dates.get("incorporated")),
            "new_owner": iso_date(dates.get("newOwnerDate")),
            "bbb_file_opened": iso_date(dates.get("bbbFileOpened")),
            "accredited": iso_date(dates.get("accredited")),
        },
        "categories": {
            "primary": {"id": clean(categories.get("primaryTobId")), "name": clean(categories.get("primaryCategoryName"))},
            "items": _titled_links(categories.get("links")),
        },
        "contact": {
            "phone": clean(contact.get("phoneNumber")),
            "additional_phones": _labelled(contact.get("additionalPhoneNumbers")),
            "fax_numbers": _labelled(contact.get("additionalFaxNumbers")),
            "text_number": clean(contact.get("textNumber")),
            "email": emails[0] if emails else None,
            "additional_emails": emails[1:],
            "websites": _websites(contact.get("additionalWebsiteAddresses")),
        },
        "people": _contacts(contact.get("contacts")),
        "address": _address(location.get("postalAddress") or location.get("displayAddress")),
        "location": {
            "formatted_address": clean(location.get("formattedAddress")),
            "latitude": number(location.get("latitude")),
            "longitude": number(location.get("longitude")),
            "is_us_based": bool(location.get("isUsBased")),
            "serving_area": html_text(location.get("servingArea")),
            "serving_areas": _serving_areas(location.get("servingAreas")),
        },
        "hours": _hours(location.get("operatingHours")),
        "headquarters": {
            "name": clean(hq.get("name") or hq.get("businessName")),
            "link": _link(hq.get("url") or hq.get("reportUrl")),
            "address": clean(hq.get("address") or hq.get("formattedAddress")),
        } if hq else None,
        "licenses": _licenses(org.get("license")),
        "social_media": _social(display.get("socialMediaList")),
        "alerts": _alerts(display.get("alerts")),
        "additional_information": texts,
        "referral_assistance": [html_text(t) for t in (display.get("referralAssistanceTexts") or []) if html_text(t)],
        "program_participation": html_text(display.get("programParticipationText")),
        "reviews_summary": {
            "count": number(summary.get("reviewsTotal")) or 0,
            "average_rating": number(average) if summary.get("displayAverageOfReviewStarRatings") and average else None,
            "are_suppressed": bool(summary.get("suppressReviews")),
            "latest": [{"id": clean(r.get("id")), "author": clean(r.get("displayName")), "preview": clean(r.get("previewText"))}
                       for r in (bp.get("latestReviews") or []) if isinstance(r, dict)],
        },
        "complaints_summary": {
            "count": number(summary.get("complaintsTotal")) or 0,
            "closed_last_3_years": number(summary.get("totalClosedComplaintsPastThreeYears")) or 0,
            "closed_last_12_months": number(summary.get("totalClosedComplaintsPastTwelveMonths")) or 0,
        },
        "locations": _locations(bp.get("dialogLocations")),
        "related_businesses": [
            {"name": clean(b.get("name") or b.get("businessName")), "link": _link(b.get("url") or b.get("reportUrl")),
             "relationship": clean(b.get("relationship") or b.get("type"))}
            for b in ((display.get("relatedBusinessList") or {}).get("relatedBusinesses") or []) if isinstance(b, dict)],
        "media": _media(bp.get("media")),
        "bbb_office": {"name": clean(local.get("name")), "link": _link(local.get("url"))} if local.get("name") else None,
        "faq": _faq(bp.get("faq")),
        "links": {
            "profile": _link(profile_path),
            "reviews": _link(urls.get("reviews")),
            "complaints": _link(urls.get("complaints")),
            "details": _link(urls.get("moreInfo")),
            "leave_review": _link(urls.get("submitReview")),
            "file_complaint": _link(urls.get("submitComplaint")),
        },
    }


# ---- customer reviews ------------------------------------------------------------

def _dated_text(text, date):
    text = html_text(text)
    date = iso_date(date)
    return {"text": text, "date": date} if (text or date) else None


def parse_review(item):
    return {
        "id": clean(item.get("id")),
        "author": clean(item.get("displayName")),
        "rating": number(item.get("reviewStarRating")),
        "date": iso_date(item.get("date")),
        "text": html_text(item.get("text")) if not item.get("extendedText") else
                html_text(" ".join([item.get("text") or ""] + [t for t in item.get("extendedText") if isinstance(t, str)])),
        "business_response": _dated_text(item.get("businessResponseText"), item.get("businessResponseDate")),
        "customer_response": _dated_text(item.get("customerResponseText"), item.get("customerResponseDate")),
        "business_rebuttal": _dated_text(item.get("businessRebuttalText"), item.get("businessRebuttalDate")),
    }


def parse_reviews(state, page):
    """A /customer-reviews tab state -> {company identity, reviews, pagination}.
    The site pages 10 at a time and publishes the total (numFound)."""
    bp = (state or {}).get("businessProfile") or {}
    block = bp.get("customerReviews") or {}
    items = [parse_review(r) for r in (block.get("items") or []) if isinstance(r, dict)]
    total = number(block.get("numFound"))
    total_pages = number(block.get("totalPages"))
    if total_pages is None and total is not None:
        total_pages = math.ceil(total / REVIEWS_PAGE_SIZE)
    return {
        "sort": clean(block.get("sort")),
        "reviews": items,
        "pagination": {
            "page": page,
            "items_per_page": REVIEWS_PAGE_SIZE,
            "total_pages": int(total_pages or 0),
            "total_count": int(total or 0),
        },
    }


# ---- complaints -------------------------------------------------------------------

def parse_complaint(item):
    responses = []
    for r in item.get("responses") or []:
        if isinstance(r, dict):
            responses.append({"from": clean(r.get("type")), "date": iso_date(r.get("date")), "text": html_text(r.get("text"))})
    return {
        "id": clean(item.get("id")),
        "type": clean(item.get("type")),
        "status": clean(item.get("status")),
        "date": iso_date(item.get("date")),
        "text": html_text(item.get("text")),
        "responses": responses,
    }


def _filter_counts(items):
    return [{"id": clean(f.get("slug")), "count": number(f.get("count"))} for f in (items or []) if isinstance(f, dict) and f.get("slug")]


def parse_complaints(state, page):
    """A /complaints tab state -> {complaints, filters with counts,
    pagination}. numFound is capped at 10,000 by the site and is -1 past the
    last page; the site serves pages up to 1000, so `has_next` follows the
    page we got rather than a total the site itself caps."""
    bp = (state or {}).get("businessProfile") or {}
    block = bp.get("customerComplaints") or {}
    items = [parse_complaint(c) for c in (block.get("items") or []) if isinstance(c, dict)]
    total = number(block.get("numFound"))
    total = total if total is not None and total >= 0 else None
    total_pages = min(COMPLAINTS_MAX_PAGE, math.ceil(total / COMPLAINTS_PAGE_SIZE)) if total is not None else None
    filters = block.get("filters") or {}
    has_next = len(items) >= COMPLAINTS_PAGE_SIZE and page < COMPLAINTS_MAX_PAGE and (total_pages is None or page < total_pages)
    return {
        "complaints": items,
        "hidden_count": number(block.get("numHidden")),
        "filters": {
            "types": _filter_counts(filters.get("type")),
            "statuses": _filter_counts(filters.get("status")),
        },
        "pagination": {
            "page": page,
            "items_per_page": COMPLAINTS_PAGE_SIZE,
            "has_next": has_next,
            "total_pages": total_pages,
            "total_count": total,
        },
    }


# ---- the suggest API -----------------------------------------------------------------

def _suggest_business(item):
    raw_id = clean(item.get("id")) or ""
    parts = raw_id.split("_")
    ident = company_id(parts[0], parts[1]) if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit() else None
    tags = [clean(t) for t in (item.get("metaTags") or []) if clean(t)]
    return {
        "id": ident,
        "name": strip_tags(item.get("title")),
        "link": _link(item.get("url")),
        "address": clean(item.get("secondaryTitle")),
        "is_accredited": "accredited" in tags and "nonaccredited" not in tags,
        "is_headquarters": "headquarters" in tags and "nonheadquarters" not in tags,
        "tags": tags,
    }


def _suggest_category(item):
    slug = clean(item.get("url"))
    tags = [clean(t) for t in (item.get("metaTags") or []) if clean(t)]
    return {
        "id": clean(item.get("entityId")),
        "name": strip_tags(item.get("title")),
        "slug": slug,
        "link": f"{SITE}/us/category/{slug}" if slug else None,
        "tags": tags,
    }


def parse_suggest_find(payload, kind=None):
    """/api/suggest/find -> businesses and/or categories. `kind` =
    "Organization" | "Category" keeps one entity type."""
    businesses, categories = [], []
    for item in payload if isinstance(payload, list) else []:
        if not isinstance(item, dict):
            continue
        etype = item.get("entityType")
        if etype == "Organization" and kind in (None, "Organization"):
            businesses.append(_suggest_business(item))
        elif etype == "Category" and kind in (None, "Category"):
            categories.append(_suggest_category(item))
    return {"businesses": businesses, "categories": categories}


def parse_suggest_location(payload):
    out = []
    for item in payload if isinstance(payload, list) else []:
        if not isinstance(item, dict):
            continue
        lat_lng = (item.get("latLng") or "").split(",")
        ident = clean(item.get("id")) or ""
        parts = ident.split("_")          # "Chicago_IL_USA" | "60654_USA" (a postal code)
        is_postal = len(parts) == 2
        out.append({
            "id": ident or None,
            "display_text": clean(item.get("displayText")),
            "city": clean(parts[0]) if len(parts) == 3 else None,
            "state": clean(parts[1]) if len(parts) == 3 else None,
            "postal_code": clean(parts[0]) if is_postal else None,
            "country": clean(item.get("country")),
            "latitude": number(lat_lng[0]) if len(lat_lng) == 2 else None,
            "longitude": number(lat_lng[1]) if len(lat_lng) == 2 else None,
            "bbb_office_id": clean(item.get("bbbId")),
        })
    return out
