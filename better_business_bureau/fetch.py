"""Better Business Bureau transport: plain curl_cffi with browser-impersonated
TLS, no browser, no login, no cookies kept between requests (the site keeps
search filters in cookies, so a kept jar would leak one caller's
accredited-only filter into the next caller's search; _get()).

Egress (config's "--- better business bureau ---" block, pod probes
2026-11-07 and 2026-11-10): the pod's own IP passes every surface, so
sessions ride direct (BETTER_BUSINESS_BUREAU_EXIT). Profile pages and their
tabs sit behind a Cloudflare managed challenge decided per exit IP AND per
TLS profile: since 2026-11-10 the curl_cffi "chrome" alias (chrome152 in the
pod's curl_cffi 0.17) is refused on every exit, chrome150 passes 8/8 on the
pod's own IP (IMPERSONATE). A clean exit stays clean. A block drops the session, the
retry rides a fresh exit, and after a block on the configured tier new
sessions ride the fallback tier (BETTER_BUSINESS_BUREAU_FALLBACK, datacenter)
for BETTER_BUSINESS_BUREAU_BLOCK_COOLDOWN seconds; a blocked call tries
BETTER_BUSINESS_BUREAU_EXIT_ATTEMPTS fresh exits (quora's ladder).

Upstream surfaces (all server-rendered JSON in window.__PRELOADED_STATE__
unless noted; better_business_bureau/parsers.py):

  * SEARCH    GET /search?find_text=&find_loc=&find_country=USA|CAN
              [&find_type=Name|Category&find_entity=<code>&page=1..15
              &sort=Relevance|Distance|Rating|AToZ|ZToA&filter_ratings=A
              &filter_category=<code>&filter_state=IL&filter_distance=5..100
              &filter_accredited=1&filter_raq=1&filter_sa=1] -> searchResult,
              15 rows per page, 15 pages at most. Always HTTP 200; a term
              with no match still returns fuzzy matches.
  * PROFILE   GET /<us|ca>/<state>/<city>/profile/<category>/<slug>-<bbbId>-<businessId>
              -> businessProfile. A URL whose tail is a known id 301s to the
              canonical path when the state segment is a real state code
              (profile_path()); the redirect DROPS the query string, so the
              tab pages are fetched on the canonical path. An unknown id is
              a real HTTP 404 ("Page not found" title).
  * REVIEWS   GET <profile>/customer-reviews?page=N&sort=<field dir>
              -> businessProfile.customerReviews (10 per page, numFound).
  * COMPLAINTS GET <profile>/complaints?page=N&type=<slug>&status=<slug>
              -> businessProfile.customerComplaints (10 per page, numFound
              capped at 10000, pages up to 1000).
  * SUGGEST   GET /api/suggest/find?country=&entityTypes=Category|Organization
              &input=[&locationInput=] and /api/suggest/location?country=
              &input=&maxMatches=10&includePostalCodes=true -> JSON lists.

Failure taxonomy (scraper_errors, mapped to HTTP by route_glue):
  BBBUpstreamError  transport failure / 5xx / page without state  — retryable
  BBBBlocked        403 / 429 / 503 or the Cloudflare challenge     — retryable on a fresh exit
  BBBBadRequest     upstream 400                                    — never retried
  BBBNotFound       HTTP 404 (unknown business id)                  — never retried
"""
import os
import sys
import threading
import time
from urllib.parse import urlencode, urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import egress
from scraper_errors import BadRequest, Blocked, NotFound, UpstreamError
from better_business_bureau import parsers
from better_business_bureau.refs import SITE, known_profile_path, remember_profile_path, stub_profile_path

# Pinned, never the generic "chrome" alias: the alias follows the installed
# curl_cffi (0.17 = chrome152), and Cloudflare refused chrome152 on every
# exit while chrome150 passed (pod probe 2026-11-10, 8 profile pages each:
# direct 8/8, US residential 3/3 exits, datacenter 2/4 exits; chrome136 4/8,
# chrome133a 2/8 on the same IP). Quora and Vrbo pin it for the same reason.
IMPERSONATE = "chrome150"
PAGE_TIMEOUT = 40        # complaint pages run to ~400 KB
JSON_TIMEOUT = 20
BLOCK_RETRY_PAUSE = 0.3  # a block is cured by a fresh exit, not by waiting

PAGE_HEADERS = {
    "accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
               "image/avif,image/webp,*/*;q=0.8"),
    "upgrade-insecure-requests": "1",
}
JSON_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "referer": SITE + "/",
}

_CHALLENGE_MARKERS = ("just a moment", "cf-chl", "challenge-platform", "attention required", "cf-mitigated")


class BBBUpstreamError(UpstreamError):
    """Transport failure, 5xx or a page without its state — retryable."""


class BBBBlocked(BBBUpstreamError, Blocked):
    """403 / 429 / 503 or the Cloudflare challenge page — retryable on a fresh exit."""


class BBBBadRequest(BadRequest):
    """Upstream 400 — never retried."""


class BBBNotFound(NotFound):
    """The business / page does not exist (HTTP 404) — never retried."""


# ---- sessions ----------------------------------------------------------------
# One session per cheroot worker thread: a curl handle must not be shared
# across threads. The session keeps its sticky exit for its lifetime (a
# clean exit stays clean); a retryable failure drops it so the retry rides a
# fresh one.
_local = threading.local()
_fallback_until = 0.0
_fallback_lock = threading.Lock()


def _proxy():
    proxy = config.better_business_bureau_proxy()
    if time.time() < _fallback_until:
        fallback = config.better_business_bureau_fallback_proxy()
        if fallback:
            proxy = fallback
    return proxy


def _session():
    sess = getattr(_local, "session", None)
    if sess is None:
        from curl_cffi import requests as curl_requests
        proxy = _proxy()
        sess = curl_requests.Session(impersonate=IMPERSONATE)
        if proxy:
            sess.proxies = {"http": proxy, "https": proxy}
        sess.headers["accept-language"] = egress.accept_language(proxy)
        sess.bbb_proxy = proxy
        _local.session = sess
    return sess


def _drop_session(blocked=False):
    """Close the thread's session so the retry rides a fresh exit. A block on
    the configured tier moves new sessions to the fallback tier for
    BETTER_BUSINESS_BUREAU_BLOCK_COOLDOWN seconds."""
    global _fallback_until
    sess = getattr(_local, "session", None)
    _local.session = None
    on_configured_tier = sess is not None and getattr(sess, "bbb_proxy", None) == config.better_business_bureau_proxy() \
        if config.BETTER_BUSINESS_BUREAU_EXIT in (None, "direct") else sess is not None
    if sess is not None:
        try:
            sess.close()
        except Exception:
            pass
    if blocked and on_configured_tier and config.BETTER_BUSINESS_BUREAU_BLOCK_COOLDOWN:
        with _fallback_lock:
            _fallback_until = max(_fallback_until, time.time() + config.BETTER_BUSINESS_BUREAU_BLOCK_COOLDOWN)


def _retrying(fn):
    """Run fn() under the retry policy: a block gets
    config.BETTER_BUSINESS_BUREAU_EXIT_ATTEMPTS tries on fresh exits with no
    backoff, any other upstream failure config.MAX_RETRIES with backoff;
    NotFound / BadRequest surface immediately."""
    last = None
    attempts = max(config.BETTER_BUSINESS_BUREAU_EXIT_ATTEMPTS, config.MAX_RETRIES)
    plain_failures = 0
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except BBBBlocked as e:
            last = e
            _drop_session(blocked=True)
            if attempt < attempts:
                time.sleep(BLOCK_RETRY_PAUSE)
        except BBBUpstreamError as e:
            last = e
            plain_failures += 1
            _drop_session()
            if plain_failures >= config.MAX_RETRIES:
                break
            time.sleep(config.RETRY_BACKOFF * plain_failures)
    raise last


# ---- classification ----------------------------------------------------------

def is_challenge(text):
    head = (text or "")[:4000].lower()
    return any(marker in head for marker in _CHALLENGE_MARKERS)


def _classify(resp, label):
    """Map an HTTP response to the error taxonomy; return the body text."""
    text = resp.text
    if resp.status_code == 404:
        raise BBBNotFound(f"{label} not found")
    if resp.status_code == 400:
        raise BBBBadRequest(text[:200])
    if resp.status_code in (401, 403, 429, 503):
        kind = "Cloudflare challenge" if is_challenge(text) else f"HTTP {resp.status_code}"
        raise BBBBlocked(f"{kind} for {label}")
    if resp.status_code != 200:
        raise BBBUpstreamError(f"HTTP {resp.status_code} for {label}")
    return text


def _get(url, label, headers, timeout, **kw):
    sess = _session()
    # The site keeps search state in cookies: after one accredited-only search
    # (filter_accredited=1) it sets iabbb_accredited_search=true and every
    # later search on that session stays accredited-only (81,335 plumbers ->
    # 13,972, 2026-11-07). Sessions are shared by every caller on the thread,
    # so each request starts with an empty jar; no surface needs a cookie
    # (the Cloudflare challenge is decided per exit IP).
    sess.cookies.clear()
    try:
        return sess.get(url, headers=headers, timeout=timeout, **kw)
    except Exception as e:
        raise BBBUpstreamError(f"request failed: {type(e).__name__}: {e}")


# ---- pages -------------------------------------------------------------------

def fetch_state_page(path, label, params=None):
    """GET a bbb.org page -> (preloaded state, html). A 200 page without the
    state is a block when it looks like a challenge, else an upstream error."""
    url = SITE + path + (("?" + urlencode(params, doseq=True)) if params else "")

    def once():
        resp = _get(url, label, PAGE_HEADERS, PAGE_TIMEOUT, allow_redirects=True)
        text = _classify(resp, label)
        state = parsers.preloaded_state(text)
        if state is None:
            if is_challenge(text):
                raise BBBBlocked(f"challenge page for {label}")
            raise BBBUpstreamError(f"no page state for {label}: {parsers.page_title(text)[:80]!r}")
        return state, text
    return _retrying(once)


def fetch_search(params):
    """GET /search?... -> (searchResult state, html)."""
    return fetch_state_page("/search", f"search {params.get('find_text', '')!r}", params)


def profile_path(ident):
    """The canonical profile path of a business id, from the process hint
    (a link the caller passed, an earlier redirect) or one redirect hop on
    the stub path. An unknown id is a 404 -> NotFound."""
    known = known_profile_path(ident)
    if known:
        return known
    stub = stub_profile_path(ident)
    label = f"business {ident}"

    def once():
        resp = _get(SITE + stub, label, PAGE_HEADERS, PAGE_TIMEOUT, allow_redirects=False)
        if resp.status_code in (301, 302, 307, 308):
            location = resp.headers.get("location") or ""
            path = urlparse(location).path if location else ""
            if "/profile/" not in path:
                raise BBBUpstreamError(f"unexpected redirect for {label}: {location[:120]!r}")
            return path.rstrip("/")
        text = _classify(resp, label)
        if parsers.preloaded_state(text) is None:
            if is_challenge(text):
                raise BBBBlocked(f"challenge page for {label}")
            raise BBBUpstreamError(f"no page state for {label}")
        return stub
    path = _retrying(once)
    remember_profile_path(ident, path)
    return path


def fetch_profile(ident):
    """GET the profile page of a business id -> (state, html)."""
    path = profile_path(ident)
    state, html = fetch_state_page(path, f"business {ident}")
    canonical = ((state.get("businessProfile") or {}).get("urls") or {}).get("profile")
    if canonical:
        remember_profile_path(ident, canonical)
    return state, html


def fetch_reviews(ident, page, sort):
    """GET <profile>/customer-reviews?page=&sort= -> (state, html)."""
    params = {"page": page}
    if sort:
        params["sort"] = sort
    return fetch_state_page(profile_path(ident) + "/customer-reviews", f"reviews of {ident} page {page}", params)


def fetch_complaints(ident, page, kind=None, status=None):
    """GET <profile>/complaints?page=&type=&status= -> (state, html)."""
    params = {"page": page}
    if kind:
        params["type"] = kind
    if status:
        params["status"] = status
    return fetch_state_page(profile_path(ident) + "/complaints", f"complaints of {ident} page {page}", params)


# ---- the suggest API ---------------------------------------------------------

def _fetch_json(path, params, label):
    url = SITE + path + "?" + urlencode(params, doseq=True)

    def once():
        resp = _get(url, label, JSON_HEADERS, JSON_TIMEOUT)
        text = _classify(resp, label)
        try:
            payload = resp.json()
        except Exception:
            if is_challenge(text):
                raise BBBBlocked(f"challenge page for {label}")
            raise BBBUpstreamError(f"non-JSON response for {label}: {text[:120]!r}")
        if not isinstance(payload, list):
            raise BBBUpstreamError(f"unexpected payload shape for {label}: {text[:120]!r}")
        return payload
    return _retrying(once)


def fetch_suggest_find(query, country, entity_types, location=None):
    """GET /api/suggest/find -> list of category / business suggestions."""
    params = [("country", country)] + [("entityTypes", t) for t in entity_types] + [("input", query)]
    if location:
        params.append(("locationInput", location))
    return _fetch_json("/api/suggest/find", params, f"suggest {query!r}")


def fetch_suggest_location(query, country, include_postal_codes=True, max_matches=10):
    """GET /api/suggest/location -> list of place suggestions."""
    params = {"country": country, "input": query, "maxMatches": max_matches,
              "includePostalCodes": "true" if include_postal_codes else "false"}
    return _fetch_json("/api/suggest/location", params, f"location suggest {query!r}")
