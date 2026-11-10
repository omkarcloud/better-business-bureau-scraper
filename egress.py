"""Egress helpers the scraper asks for: the Accept-Language header of a
session. The hosted API derives it from the country of the proxy exit it
leaves through; this open-source server runs direct (or through your own
BETTER_BUSINESS_BUREAU_PROXY), so it announces a plain US English
preference, which is what bbb.org serves for the US and Canada.
"""

DEFAULT_ACCEPT_LANGUAGE = "en-US,en;q=0.9"


def accept_language(proxy=None, country=None):
    """The Accept-Language for a session on `proxy` (ignored here)."""
    return DEFAULT_ACCEPT_LANGUAGE


def site_accept_language(site):
    """The Accept-Language for a site's module-level headers."""
    return DEFAULT_ACCEPT_LANGUAGE
