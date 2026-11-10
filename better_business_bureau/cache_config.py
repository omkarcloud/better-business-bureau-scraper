"""Cache TTL per /better-business-bureau/* endpoint (cache.py, keyed on the
validated params). BBB profiles move slowly: a rating changes when a
complaint closes or a review lands, accreditation and licences on a
yearly cadence, so hours of caching never serve a materially stale record.
"""
from datetime import timedelta

# One row per business id: the parsed profile page (companies/details).
COMPANY_CACHE = timedelta(hours=12)
# The canonical profile path of an id: it changes only when a business moves
# or renames, and a stale one still 301s to the new path.
PROFILE_PATH_CACHE = timedelta(days=7)
# A review page: new reviews land daily on big businesses; page 1 moves most.
REVIEWS_CACHE = timedelta(hours=3)
# A complaint page: same cadence as reviews.
COMPLAINTS_CACHE = timedelta(hours=3)
# Search / category pages: the ranking reorders as businesses are added.
SEARCH_CACHE = timedelta(hours=6)
# Typeahead suggestions: the vocabulary (categories, places) is near static,
# business names rarely change.
SUGGEST_CACHE = timedelta(hours=24)
# A category slug -> code resolution: the category tree is static.
CATEGORY_CODE_CACHE = timedelta(days=7)
