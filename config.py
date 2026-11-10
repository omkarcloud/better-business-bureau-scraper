"""Configuration for the Better Business Bureau Scraper. Everything can be set
with an environment variable; the defaults work out of the box.

    PORT                          port the API listens on (default 8000)
    BETTER_BUSINESS_BUREAU_PROXY  proxy URL for every request, e.g.
                                  http://user:pass@host:port (default: none,
                                  direct). bbb.org's search pages and
                                  typeahead answer any connection; its business
                                  profile pages sit behind Cloudflare, which
                                  decides per IP. They open from most home and
                                  office connections, so you very likely don't
                                  need this. If profile, review or complaint
                                  calls answer 502 "blocked", set a residential
                                  proxy here.

Everything else below is a plain constant with a working default — edit it
here if you need to.
"""
import os

PORT = int(os.environ.get("PORT", "8000"))

# Retry policy for transport errors (every request).
MAX_RETRIES = 3
RETRY_BACKOFF = 2          # seconds, multiplied by the attempt number

BETTER_BUSINESS_BUREAU_PROXY = os.environ.get("BETTER_BUSINESS_BUREAU_PROXY") or None

# "direct" or "proxy": only tells the scraper which kind of exit it rides.
BETTER_BUSINESS_BUREAU_EXIT = "proxy" if BETTER_BUSINESS_BUREAU_PROXY else "direct"
# A Cloudflare challenge drops the session and retries on a fresh one this many
# times (a rotating proxy URL gives each retry a new IP).
BETTER_BUSINESS_BUREAU_EXIT_ATTEMPTS = 3
# The hosted API switches to a second exit pool after a block; this server has
# one exit (yours), so the switch is off.
BETTER_BUSINESS_BUREAU_BLOCK_COOLDOWN = 0


def better_business_bureau_proxy():
    """The proxy URL for one session (None = direct)."""
    return os.environ.get("BETTER_BUSINESS_BUREAU_PROXY") or None


def better_business_bureau_fallback_proxy():
    """No second exit pool here (None = keep the session's own exit)."""
    return None
