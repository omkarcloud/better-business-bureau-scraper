"""Offline tests for the Better Business Bureau transport.

    python -m pytest better_business_bureau/test_fetch.py -q

No network: the thread's curl session is replaced by a fake.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from better_business_bureau import fetch  # noqa: E402


class _Jar(dict):
    def clear(self):
        self.cleared = getattr(self, "cleared", 0) + 1
        super().clear()


class _Resp:
    status_code = 200
    text = '<script>window.__PRELOADED_STATE__ = {"searchResult": {"results": []}};</script>'


class _Session:
    def __init__(self):
        self.cookies = _Jar(iabbb_accredited_search="true")
        self.jar_at_request = []

    def get(self, url, **kw):
        self.jar_at_request.append(dict(self.cookies))
        self.cookies["iabbb_accredited_search"] = "true"   # what the site sets after a filtered search
        return _Resp()


def test_every_request_starts_with_an_empty_cookie_jar(monkeypatch):
    sess = _Session()
    monkeypatch.setattr(fetch, "_session", lambda: sess)
    fetch.fetch_search({"find_text": "plumber", "find_country": "USA", "filter_accredited": "1"})
    fetch.fetch_search({"find_text": "plumber", "find_country": "USA"})
    assert sess.jar_at_request == [{}, {}]
    assert sess.cookies.cleared == 2
